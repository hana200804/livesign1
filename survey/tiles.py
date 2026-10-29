"""Bộ đọc phần Point của MVT, thuần Python. Chỉ dùng khám phá ảnh/nhãn gợi ý."""

from __future__ import annotations

import math
import struct


def varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("MVT bị cắt ngắn.")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError("MVT varint vượt 64 bit.")
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError("MVT varint vượt 64 bit.")


def fields(data: bytes) -> list[tuple[int, int | bytes]]:
    result = []
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("MVT field ID không hợp lệ.")
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            value = data[offset : offset + length]
            offset += length
            if len(value) != length:
                raise ValueError("MVT fixed field bị cắt ngắn.")
        elif wire == 2:
            length, offset = varint(data, offset)
            value = data[offset : offset + length]
            offset += length
            if len(value) != length:
                raise ValueError("MVT length field bị cắt ngắn.")
        else:
            raise ValueError("MVT dùng wire type chưa hỗ trợ.")
        result.append((number, value))
    return result


def packed(data: bytes) -> list[int]:
    result, offset = [], 0
    while offset < len(data):
        value, offset = varint(data, offset)
        result.append(value)
    return result


def zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def byte_value(value: int | bytes) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("MVT field cần dữ liệu bytes.")
    return value


def integer_value(value: int | bytes) -> int:
    if not isinstance(value, int):
        raise ValueError("MVT field cần số nguyên.")
    return value


def decode_value(data: bytes):
    values = fields(data)
    if len(values) != 1:
        raise ValueError("MVT value cần một giá trị.")
    number, value = values[0]
    if number == 1:
        return byte_value(value).decode("utf-8")
    if number == 2:
        return struct.unpack("<f", byte_value(value))[0]
    if number == 3:
        return struct.unpack("<d", byte_value(value))[0]
    if number == 4:
        value = integer_value(value)
        return value - 2**64 if value >= 2**63 else value
    if number == 5:
        return integer_value(value)
    if number == 6:
        return zigzag(integer_value(value))
    if number == 7:
        return bool(integer_value(value))
    raise ValueError("MVT value type chưa hỗ trợ.")


def tile_point(x: int, y: int, z: int, extent: int, px: int, py: int) -> list[float]:
    if extent <= 0:
        raise ValueError("MVT extent phải > 0.")
    longitude = (x + px / extent) / 2**z * 360 - 180
    mercator_y = math.pi * (1 - 2 * (y + py / extent) / 2**z)
    latitude = math.degrees(math.atan(math.sinh(mercator_y)))
    return [longitude, latitude]


def decode_points(payload: bytes, x: int, y: int, z: int) -> dict[str, list[dict]]:
    layers = {}
    for field, raw_layer in fields(payload):
        if field != 3 or not isinstance(raw_layer, bytes):
            continue
        layer_fields = fields(raw_layer)
        name = next(
            byte_value(value).decode("utf-8") for number, value in layer_fields if number == 1
        )
        keys = [byte_value(value).decode("utf-8") for number, value in layer_fields if number == 3]
        values = [decode_value(byte_value(value)) for number, value in layer_fields if number == 4]
        extent = next((integer_value(value) for number, value in layer_fields if number == 5), 4096)
        features = []
        for number, raw_feature in layer_fields:
            if number != 2:
                continue
            feature_fields = fields(byte_value(raw_feature))
            kind = next((value for key, value in feature_fields if key == 3), None)
            if kind != 1:
                continue
            tags = [
                item
                for key, value in feature_fields
                if key == 2
                for item in packed(byte_value(value))
            ]
            if len(tags) % 2:
                raise ValueError("MVT tags thiếu cặp key/value.")
            try:
                properties = {
                    keys[tags[index]]: values[tags[index + 1]] for index in range(0, len(tags), 2)
                }
            except IndexError:
                raise ValueError("MVT tags trỏ index ngoài miền.") from None
            commands = [
                item
                for key, value in feature_fields
                if key == 4
                for item in packed(byte_value(value))
            ]
            if len(commands) != 3 or commands[0] != 9:
                raise ValueError("Cần Point MVT một điểm; không nhận multipoint như ảnh độc lập.")
            location = tile_point(x, y, z, extent, zigzag(commands[1]), zigzag(commands[2]))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": location},
                    "properties": properties,
                }
            )
        layers[name] = features
    return layers
