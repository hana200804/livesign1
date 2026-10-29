import pytest

from survey.tiles import decode_points, decode_value, fields, packed, tile_point, varint, zigzag


def encode_varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def wire(number, value):
    return (
        encode_varint(number << 3) + encode_varint(value)
        if isinstance(value, int)
        else encode_varint((number << 3) | 2) + encode_varint(len(value)) + value
    )


def test_point_tile_preserves_large_ids_and_photographer():
    feature = wire(2, b"\x00\x00\x01\x01") + wire(3, 1) + wire(4, b"\x09\x00\x00")
    layer = (
        wire(15, 2)
        + wire(1, b"image")
        + wire(2, feature)
        + wire(3, b"id")
        + wire(3, b"creator_id")
        + wire(4, wire(5, 9_007_199_254_740_993))
        + wire(4, wire(1, b"person"))
        + wire(5, 4096)
    )
    decoded = decode_points(wire(3, layer), 13009, 7212, 14)["image"][0]
    assert decoded["properties"]["id"] == 9_007_199_254_740_993
    assert decoded["properties"]["creator_id"] == "person"
    assert decoded["geometry"]["coordinates"] == tile_point(13009, 7212, 14, 4096, 0, 0)


@pytest.mark.parametrize("payload", [b"\x80", b"\x80" * 11])
def test_truncated_or_oversize_varint_is_rejected(payload):
    with pytest.raises(ValueError):
        varint(payload)


def test_zigzag_handles_negative_tile_offsets():
    assert [zigzag(value) for value in range(6)] == [0, -1, 1, -2, 2, -3]


def test_fields_reject_truncated_bytes_and_unknown_wire_type():
    with pytest.raises(ValueError):
        fields(b"\x0a\x05a")
    with pytest.raises(ValueError):
        fields(b"\x0f")
    assert packed(b"\x01\x80\x01") == [1, 128]


@pytest.mark.parametrize("number", [1, 2, 3])
def test_mvt_string_or_float_cannot_use_integer_wire_value(number):
    with pytest.raises(ValueError, match="bytes"):
        decode_value(wire(number, 42))


@pytest.mark.parametrize("number", [4, 5, 6, 7])
def test_mvt_integer_or_boolean_cannot_use_bytes_wire_value(number):
    with pytest.raises(ValueError, match="số nguyên"):
        decode_value(wire(number, b"not an integer"))


@pytest.mark.parametrize("field", [1, 2, 3, 4, 5])
def test_mvt_layer_rejects_wrong_wire_type(field):
    layer = (b"" if field == 1 else wire(1, b"image")) + wire(field, b"bad" if field == 5 else 1)
    with pytest.raises(ValueError):
        decode_points(wire(3, layer), 0, 0, 0)
