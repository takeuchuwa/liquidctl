import pytest

from _testutils import MockHidapiDevice, MockPyusbDevice, Report

import json
from types import SimpleNamespace

from PIL import Image, ImageDraw

import liquidctl.driver.asus_ryujin_lcd as asus_ryujin_lcd
from liquidctl.driver.asus_ryujin import AsusRyujin
from liquidctl.error import ExpectationNotMet, Timeout
from liquidctl.driver.asus_ryujin_lcd import (
    _build_mjpeg_avi,
    _format_lcd_value,
    _iter_lcd_animation,
    _load_lcd_stats_config,
    _load_lcd_static_background,
    _parse_lcd_color,
    _prepare_lcd_frame,
    _prepare_lcd_stored_animation,
    _prepare_lcd_stored_image,
    _read_lcd_custom_stats,
    _render_lcd_stats,
)

PROTOCOL_HEADER = 0xEC
CMD_GET_FIRMWARE = 0x82
CMD_GET_STATUS = 0x99
CMD_GET_PUMP_DUTY = 0x9A
CMD_GET_FAN_SPEEDS = 0xA0
CMD_GET_FAN_DUTY = 0xA1
CMD_SET_PUMP_DUTY = 0x1A
CMD_SET_FAN_DUTY = 0x21
CMD_GET_LCD_MODE = 0xD0
CMD_SET_LCD_MODE = 0x51
CMD_ANNOUNCE_LCD_FRAME = 0x7F
CMD_GET_LCD_SETTINGS = 0xDC
CMD_SET_LCD_SETTINGS = 0x5C
CMD_SET_LCD_LAYOUT = 0x5D
CMD_SET_LCD_TEXT_STYLE = 0x5E
CMD_SET_LCD_TEXT = 0x5F
CMD_LCD_STORAGE_OPEN = 0x71
CMD_LCD_STORAGE_INFO = 0xF1
CMD_LCD_STORAGE_SLOT = 0x72
CMD_LCD_TRANSFER = 0x73
NOTIFY_HEADER = 0xEE
DEVICE_CONFIGS = {
    0x1988: {
        "name": "Mock ASUS Ryujin II",
        "fan_count": 4,
        "pump_speed_offset": 5,
        "pump_fan_speed_offset": 7,
        "temp_offset": 3,
        "duty_channel": 0,
        "responses": {
            CMD_GET_FIRMWARE: "ec02004155524a312d533735302d30313034",
            CMD_GET_STATUS: "ec19001b056405100e",
            CMD_GET_PUMP_DUTY: "ec1a0000223c",
            CMD_GET_FAN_SPEEDS: "ec200000000c03ee02",
            CMD_GET_FAN_DUTY: "ec2100005b",
            CMD_SET_PUMP_DUTY: "ec1a",
            CMD_SET_FAN_DUTY: "ec21",
        },
        "expected_firmware": "AURJ1-S750-0104",
        "expected_status": [
            ("Liquid temperature", 27.5, "°C"),
            ("Pump speed", 1380, "rpm"),
            ("Pump fan speed", 3600, "rpm"),
            ("Pump duty", 34, "%"),
            ("Pump fan duty", 60, "%"),
            ("External fan duty", 36, "%"),
            ("External fan 1 speed", 780, "rpm"),
            ("External fan 2 speed", 750, "rpm"),
            ("External fan 3 speed", 0, "rpm"),
            ("External fan 4 speed", 0, "rpm"),
        ],
    },
    0x1BCB: {
        "name": "Mock Ryujin III EXTREME",
        "fan_count": 0,
        "pump_speed_offset": 7,
        "pump_fan_speed_offset": 10,
        "temp_offset": 5,
        "duty_channel": 1,
        "responses": {
            CMD_GET_FIRMWARE: "ec02004155524a332d533546392d30313034",
            CMD_GET_STATUS: "ec190000001d09ec041e6603",
            CMD_GET_PUMP_DUTY: "ec1a00011e1e",
            CMD_GET_LCD_MODE: "ec50000131140000",
            CMD_SET_PUMP_DUTY: "ec1a",
            # replies and notifications captured from a real cooler
            CMD_SET_LCD_MODE: "ec51",
            CMD_GET_LCD_SETTINGS: "ec5c0000003c0000003c14000000003c14",
            CMD_SET_LCD_SETTINGS: "ec5c",
            CMD_SET_LCD_LAYOUT: "ec5d",
            CMD_SET_LCD_TEXT_STYLE: "ec5e",
            CMD_SET_LCD_TEXT: "ec5f",
            CMD_LCD_STORAGE_OPEN: "ec71",
            CMD_LCD_STORAGE_INFO: "ec710001e0fe000018f70000200f0000002007",
            CMD_LCD_STORAGE_SLOT: "ec72",
            CMD_LCD_TRANSFER: "ec73",
            CMD_ANNOUNCE_LCD_FRAME: "ec7f000010",
        },
        "notifications": {
            CMD_LCD_STORAGE_OPEN: "ee12",
            CMD_LCD_TRANSFER: "ee13",
        },
        "expected_firmware": "AURJ3-S5F9-0104",
        "expected_status": [
            ("Liquid temperature", 29.9, "°C"),
            ("Pump speed", 1260, "rpm"),
            ("Pump fan speed", 870, "rpm"),
            ("Pump duty", 30, "%"),
            ("Pump fan duty", 30, "%"),
        ],
    },
    0x1ADE: {
        "name": "Mock Ryujin III EVA EDITION",
        "fan_count": 0,
        "pump_speed_offset": 7,
        "pump_fan_speed_offset": 10,
        "temp_offset": 5,
        "duty_channel": 1,
        "responses": {
            CMD_GET_FIRMWARE: "ec02004155524a322d533735302d30313039",
            CMD_GET_STATUS: "ec1900000021002e0e644803",
            CMD_GET_PUMP_DUTY: "ec1a0001281e",
            CMD_SET_PUMP_DUTY: "ec1a",
        },
        "expected_firmware": "AURJ2-S750-0109",
        "expected_status": [
            ("Liquid temperature", 33.0, "°C"),
            ("Pump speed", 3630, "rpm"),
            ("Pump fan speed", 840, "rpm"),
            ("Pump duty", 40, "%"),
            ("Pump fan duty", 30, "%"),
        ],
    },
    0x1AA2: {
        "name": "Mock Ryujin III 360",
        "fan_count": 0,
        "pump_speed_offset": 7,
        "pump_fan_speed_offset": 10,
        "temp_offset": 5,
        "duty_channel": 1,
        "responses": {
            CMD_GET_FIRMWARE: "ec02004155524a332d533546392d30313034",
            CMD_GET_STATUS: "ec190000001d09ec041e6603",
            CMD_GET_PUMP_DUTY: "ec1a00011e1e",
            CMD_SET_PUMP_DUTY: "ec1a",
        },
        "expected_firmware": "AURJ3-S5F9-0104",
        "expected_status": [
            ("Liquid temperature", 29.9, "°C"),
            ("Pump speed", 1260, "rpm"),
            ("Pump fan speed", 870, "rpm"),
            ("Pump duty", 30, "%"),
            ("Pump fan duty", 30, "%"),
        ],
    },
    0x1ADA: {
        "name": "Mock Ryujin III WHITE EDITION",
        "fan_count": 0,
        "pump_speed_offset": 7,
        "pump_fan_speed_offset": 10,
        "temp_offset": 5,
        "duty_channel": 1,
        "responses": {
            CMD_GET_FIRMWARE: "ec02004155524a332d533546392d30313034",
            CMD_GET_STATUS: "ec190000001d09ec041e6603",
            CMD_GET_PUMP_DUTY: "ec1a00011e1e",
            CMD_SET_PUMP_DUTY: "ec1a",
        },
        "expected_firmware": "AURJ2-S750-0108",
        "expected_status": [
            ("Liquid temperature", 29.9, "°C"),
            ("Pump speed", 1260, "rpm"),
            ("Pump fan speed", 870, "rpm"),
            ("Pump duty", 30, "%"),
            ("Pump fan duty", 30, "%"),
        ],
    },
}


class _MockRyujinDevice(MockHidapiDevice):
    def __init__(self, vendor_id: int, product_id: int):
        super().__init__(vendor_id, product_id)
        self.requests = []
        self.response = None
        self.lcd_mode = None
        self.player_hangs = False
        self.refuse_transfers = 0
        self.config = DEVICE_CONFIGS.get(product_id, {})

    def write(self, data):
        super().write(data)
        self.requests.append(data)

        assert data[0] == PROTOCOL_HEADER
        command = data[1]

        self.response = self.config.get("responses", {}).get(command)
        self.notification = self.config.get("notifications", {}).get(command)
        self.replied = False

        if command == CMD_SET_LCD_MODE and not self.player_hangs:
            self.lcd_mode = data[2]
        if command == CMD_GET_LCD_MODE and self.lcd_mode is not None:
            self.response = f"ec50000131{self.lcd_mode:02x}010001"
        if command == CMD_LCD_TRANSFER and data[2] == 0x01 and self.refuse_transfers > 0:
            self.refuse_transfers -= 1
            self.notification = "ee131001"

    def read(self, length, **kwargs):
        pre = super().read(length, **kwargs)
        if pre:
            return pre

        buf = bytearray(65)
        buf[0] = PROTOCOL_HEADER

        # the cooler follows some replies with an unsolicited notification
        if self.replied and self.notification:
            notification = bytes.fromhex(self.notification)
            buf[: len(notification)] = notification
            self.notification = None
            return buf[:length]
        self.replied = True

        if self.response:
            response = bytes.fromhex(self.response)
            buf[: len(response)] = response

        return buf[:length]


def _create_mock_ryujin(product_id):
    config = DEVICE_CONFIGS[product_id]
    return AsusRyujin(
        _MockRyujinDevice(vendor_id=0x0B05, product_id=product_id),
        config["name"],
        fan_count=config["fan_count"],
        pump_speed_offset=config["pump_speed_offset"],
        pump_fan_speed_offset=config["pump_fan_speed_offset"],
        temp_offset=config["temp_offset"],
        duty_channel=config["duty_channel"],
    )


def test_prepare_lcd_frame_preserves_pixel_positions_and_rgb_order(tmp_path):
    width, height = 640, 480
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width // 2 - 1, height // 2 - 1), fill=(255, 0, 0))
    draw.rectangle((width // 2, 0, width - 1, height // 2 - 1), fill=(0, 255, 0))
    draw.rectangle((0, height // 2, width // 2 - 1, height - 1), fill=(0, 0, 255))
    draw.rectangle((width // 2, height // 2, width - 1, height - 1), fill=(255, 255, 255))
    path = tmp_path / "corners.png"
    image.save(path)

    frame = _prepare_lcd_frame(path)
    row_size = width * 3

    assert len(frame) == width * height * 3
    assert frame[0:3] == bytes((255, 0, 0))
    assert frame[row_size - 3 : row_size] == bytes((0, 255, 0))
    assert frame[-row_size : -row_size + 3] == bytes((0, 0, 255))
    assert frame[-3:] == bytes((255, 255, 255))


def test_set_static_screen_uses_validated_lcd_sequence(mock_ryujin3, tmp_path):
    image = Image.new("RGB", (640, 480), color=(255, 0, 0))
    path = tmp_path / "red.png"
    image.save(path)
    bulk_device = MockPyusbDevice(vendor_id=0x0B05, product_id=0x1BCB)
    mock_ryujin3._bulk_device = bulk_device

    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="static", value=path)

    assert [request[1] for request in mock_ryujin3.device.requests[-3:]] == [
        CMD_GET_LCD_MODE,
        CMD_SET_LCD_MODE,
        CMD_ANNOUNCE_LCD_FRAME,
    ]
    assert mock_ryujin3.device.requests[-2][2:5] == [0x20, 0x00, 0x00]
    assert mock_ryujin3.device.requests[-1][2:7] == [0x03, 0x00, 0x10, 0x0E, 0x00]
    transfer, endpoint, frame = bulk_device._sent_xfers[-1]
    assert transfer == "write"
    assert endpoint == 0x02
    assert len(frame) == 640 * 480 * 3
    assert frame[:3] == bytes((255, 0, 0))


class _AcknowledgingBulkDevice(MockPyusbDevice):
    """Bulk interface whose writes are acknowledged on the HID interface."""

    def __init__(self, hid_device, **kwargs):
        super().__init__(**kwargs)
        self.hid_device = hid_device

    def write(self, endpoint, data, **kwargs):
        super().write(endpoint, data, **kwargs)
        self.hid_device.preload_read(Report(NOTIFY_HEADER, [0x14, 0x00, 0x00, 0x10]))
        return len(data)


def _lcd_requests(device):
    """Return sent reports with their zero padding removed."""
    return [bytes(request).rstrip(b"\0").hex() for request in device.requests]


def test_set_lcd_brightness_reads_settings_before_writing_them(mock_ryujin3):
    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="brightness", value="30")

    assert _lcd_requests(mock_ryujin3.device) == [
        "ecdc",
        "ec5c0100001e0000001e14000000001e14",
    ]


def test_set_lcd_off_only_changes_the_display_mode(mock_ryujin3):
    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="off", value=None)

    assert _lcd_requests(mock_ryujin3.device) == ["ec51"]


def test_set_lcd_text_uses_the_firmware_text_layout(mock_ryujin3):
    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="text", value="Liquid=34.0℃")

    requests = _lcd_requests(mock_ryujin3.device)
    # as sent by the vendor software: an 18 byte label followed by the UTF-8 value
    assert requests[0] == "ec5f00004c697175696400000000000000000000000033342e30e28483"
    assert requests[1] == "ec5e000000000101ffffff00ffffff01ffffff00ffffff01ffffff00ffffff"
    assert requests[2] == "ec5d0001210001000005"
    assert requests[3] == "ec511f"


def test_set_lcd_text_requires_a_label_and_a_value(mock_ryujin3):
    with mock_ryujin3.connect():
        with pytest.raises(ValueError, match="LABEL=VALUE"):
            mock_ryujin3.set_screen(channel="lcd", mode="text", value="no separator")

    assert not mock_ryujin3.device.requests


def test_stored_static_screen_uploads_a_jpeg_in_padded_blocks(mock_ryujin3, tmp_path, monkeypatch):
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    path = tmp_path / "noise.png"
    Image.effect_noise((640, 480), 64).save(path)
    expected = _prepare_lcd_stored_image(path)
    assert len(expected) > 4096 and len(expected) % 4096
    mock_ryujin3.device.lcd_mode = 0x11
    bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )
    mock_ryujin3._bulk_device = bulk_device

    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="stored-static", value=path)

    size = len(expected).to_bytes(3, byteorder="little").hex()
    assert _lcd_requests(mock_ryujin3.device) == [
        "ecd0",
        "ec710101",
        "ecf1",
        "ec720101",
        "ec7301",
        bytes.fromhex(f"ec7f02{size}").rstrip(b"\0").hex(),
        "ec73ff",
        "ec5d0001110100000005",
        "ec511101",
        "ecd0",
    ]
    blocks = [data for _, endpoint, data in bulk_device._sent_xfers if endpoint == 0x02]
    assert all(len(block) == 4096 for block in blocks)
    assert b"".join(blocks)[: len(expected)] == expected
    assert not any(b"".join(blocks)[len(expected) :])


def test_stored_gif_screen_uploads_a_motion_jpeg_avi(mock_ryujin3, tmp_path, monkeypatch):
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    path = tmp_path / "blink.gif"
    frames = [Image.new("RGB", (64, 48), color) for color in ("red", "blue", "green")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    mock_ryujin3.device.lcd_mode = 0x11
    bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )
    mock_ryujin3._bulk_device = bulk_device

    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=path)

    requests = _lcd_requests(mock_ryujin3.device)
    assert requests[3] == "ec7201"
    assert requests[-3:] == ["ec5d0001140100000001", "ec511401", "ecd0"]
    uploaded = b"".join(data for _, endpoint, data in bulk_device._sent_xfers if endpoint == 0x02)
    assert uploaded[:4] == b"RIFF" and uploaded[8:12] == b"AVI "


def test_stored_screen_without_a_file_shows_what_the_cooler_already_holds(mock_ryujin3):
    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=None)

    assert _lcd_requests(mock_ryujin3.device) == ["ec5d0001140100000001", "ec511401", "ecd0"]


def test_failed_lcd_upload_closes_the_transfer_exactly_once(mock_ryujin3, tmp_path, monkeypatch):
    # ending a transfer that is not open makes the cooler reboot
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_NOTIFY_TIMEOUT_MS", 50)
    path = tmp_path / "red.png"
    Image.new("RGB", (640, 480), "red").save(path)
    # a bulk interface that never acknowledges its blocks
    mock_ryujin3._bulk_device = MockPyusbDevice(vendor_id=0x0B05, product_id=0x1BCB)

    with mock_ryujin3.connect():
        with pytest.raises(Timeout):
            mock_ryujin3.set_screen(channel="lcd", mode="stored-static", value=path)

    assert _lcd_requests(mock_ryujin3.device).count("ec73ff") == 1


def _blink_gif(tmp_path):
    path = tmp_path / "blink.gif"
    frames = [Image.new("RGB", (64, 48), color) for color in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return path


def test_stored_video_is_stopped_before_it_is_replaced(mock_ryujin3, tmp_path, monkeypatch):
    # the cooler refuses to replace the video it is currently playing
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_RETRY_DELAY", 0)
    mock_ryujin3.device.lcd_mode = 0x14
    mock_ryujin3._bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )

    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=_blink_gif(tmp_path))

    assert _lcd_requests(mock_ryujin3.device)[:3] == ["ecd0", "ec51", "ec710101"]


def test_refused_lcd_transfer_is_closed_without_sending_data(mock_ryujin3, tmp_path, monkeypatch):
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_RETRY_DELAY", 0)
    mock_ryujin3.device.lcd_mode = 0x11
    mock_ryujin3.device.refuse_transfers = 100
    bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )
    mock_ryujin3._bulk_device = bulk_device

    with mock_ryujin3.connect():
        with pytest.raises(ExpectationNotMet):
            mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=_blink_gif(tmp_path))

    requests = _lcd_requests(mock_ryujin3.device)
    # every refused attempt is closed, and nothing is closed twice
    assert requests.count("ec7301") == requests.count("ec73ff") == 6
    assert requests[-2:] == ["ec7301", "ec73ff"]
    assert not bulk_device._sent_xfers


def test_refused_lcd_transfer_is_retried(mock_ryujin3, tmp_path, monkeypatch):
    # a video that was just playing is released a moment after the mode change
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_RETRY_DELAY", 0)
    mock_ryujin3.device.lcd_mode = 0x14
    mock_ryujin3.device.refuse_transfers = 2
    bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )
    mock_ryujin3._bulk_device = bulk_device

    with mock_ryujin3.connect():
        mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=_blink_gif(tmp_path))

    requests = _lcd_requests(mock_ryujin3.device)
    assert requests.count("ec7301") == 3
    assert requests.count("ec73ff") == 3
    assert bulk_device._sent_xfers
    assert requests[-3:-1] == ["ec5d0001140100000001", "ec511401"]


def test_stored_video_the_player_cannot_parse_is_reported(mock_ryujin3, tmp_path, monkeypatch):
    # a hung player leaves the display mode unchanged
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_STORED_PREPARE_DELAY", 0)
    monkeypatch.setattr("liquidctl.driver.asus_ryujin._LCD_MODE_CHANGE_TIMEOUT", 0)
    mock_ryujin3.device.lcd_mode = 0x11
    mock_ryujin3.device.player_hangs = True
    mock_ryujin3._bulk_device = _AcknowledgingBulkDevice(
        mock_ryujin3.device, vendor_id=0x0B05, product_id=0x1BCB
    )

    with mock_ryujin3.connect():
        with pytest.raises(ExpectationNotMet):
            mock_ryujin3.set_screen(channel="lcd", mode="stored-gif", value=_blink_gif(tmp_path))


def test_motion_jpeg_avi_matches_the_layout_of_vendor_uploads():
    # the cooler's player hangs on an AVI whose frame data starts elsewhere
    avi = _build_mjpeg_avi([b"\xff\xd8\xff\xd9"] * 3, fps=10)

    assert avi.index(b"LIST", 12) == 0x0C and avi[0x14:0x18] == b"hdrl"
    assert int.from_bytes(avi[0x10:0x14], "little") == 4588
    assert avi[0x1200:0x1204] == b"LIST" and avi[0x1208:0x120C] == b"INFO"
    assert avi[0x1622:0x1626] == b"LIST" and avi[0x162A:0x162E] == b"movi"
    assert int.from_bytes(avi[0x2C:0x30], "little") == 0x910  # flags


def test_invalid_stored_asset_does_not_start_a_transfer(mock_ryujin3, tmp_path):
    with mock_ryujin3.connect():
        with pytest.raises(ValueError, match="invalid stored-static configuration"):
            mock_ryujin3.set_screen(
                channel="lcd", mode="stored-static", value=tmp_path / "missing.png"
            )

    assert not mock_ryujin3.device.requests


def test_stored_animation_is_a_valid_motion_jpeg_avi(tmp_path):
    path = tmp_path / "blink.gif"
    frames = [Image.new("RGB", (64, 48), color) for color in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=50, loop=0)

    avi = _prepare_lcd_stored_animation(path)

    assert avi[:4] == b"RIFF" and avi[8:12] == b"AVI "
    assert int.from_bytes(avi[4:8], "little") == len(avi) - 8
    # main header: frame period for 20 fps, frame count and native resolution
    assert int.from_bytes(avi[32:36], "little") == 50_000
    assert int.from_bytes(avi[48:52], "little") == 2
    assert int.from_bytes(avi[64:68], "little") == 640
    assert int.from_bytes(avi[68:72], "little") == 480
    # each frame once in the data and once in the index, plus the reserved index space
    assert avi.count(b"00dc") == 5
    assert avi.count(b"\xff\xd8\xff") == 2


def test_motion_jpeg_avi_pads_odd_sized_frames():
    avi = _build_mjpeg_avi([b"\xff\xd8\xff", b"\xff\xd8"], fps=10)

    assert len(avi) % 2 == 0
    assert int.from_bytes(avi[4:8], "little") == len(avi) - 8


@pytest.mark.parametrize("mode", ["static", "gif"])
def test_invalid_lcd_asset_does_not_switch_to_raw_mode(mock_ryujin3, tmp_path, mode):
    path = tmp_path / f"missing.{mode}"

    with mock_ryujin3.connect():
        with pytest.raises(ValueError, match=f"invalid {mode} configuration"):
            mock_ryujin3.set_screen(channel="lcd", mode=mode, value=path)

    assert not mock_ryujin3.device.requests


def test_invalid_stats_background_does_not_switch_to_raw_mode(mock_ryujin3, tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"background": "missing.gif"}))

    with mock_ryujin3.connect():
        with pytest.raises(ValueError, match="invalid stats configuration"):
            mock_ryujin3.set_screen(channel="lcd", mode="stats", value=path)

    assert not mock_ryujin3.device.requests


def test_lcd_animation_frames_are_converted_and_keep_their_duration(tmp_path):
    path = tmp_path / "two-frames.gif"
    Image.new("RGB", (640, 480), color=(255, 0, 0)).save(
        path,
        save_all=True,
        append_images=[Image.new("RGB", (640, 480), color=(0, 0, 255))],
        duration=[50, 100],
        loop=0,
    )

    frames = _iter_lcd_animation(path)
    first_frame, first_duration = next(frames)
    second_frame, second_duration = next(frames)

    assert first_frame[:3] == bytes((255, 0, 0))
    assert first_duration == 0.05
    assert second_frame[:3] == bytes((0, 0, 255))
    assert second_duration == 0.1


def test_lcd_statistics_renderer_returns_a_full_nonblank_frame(tmp_path):
    background_path = tmp_path / "background.png"
    Image.new("RGB", (640, 480), color=(1, 2, 3)).save(background_path)
    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {
                "background_color": "100713",
                "font_color": "B300FF",
                "background_opacity": 0.2,
                "interval": 3,
                "title": "COOLER",
                "background": "background.png",
                "layout": {
                    "liquid": {
                        "background_color": "210B2D",
                        "background_opacity": 0.2,
                        "offset_x": -4,
                        "offset_y": 6,
                        "font_color": "B300FF",
                        "stats": [{"stat": "liquid_temperature", "indicator": "LIQUID"}],
                    }
                },
            }
        )
    )
    config = _load_lcd_stats_config(path, None)
    background = _load_lcd_static_background(config["background"])
    frame = _render_lcd_stats(
        [
            ("Liquid temperature", 29.9, "°C"),
            ("Pump speed", 1260, "rpm"),
            ("Pump fan speed", 870, "rpm"),
        ],
        config,
        0,
        3,
        background,
    )

    assert config["background_color"] == (16, 7, 19)
    assert config["font_color"] == (179, 0, 255)
    assert config["background_opacity"] == 0.2
    assert config["interval"] == 3
    assert config["title"] == "COOLER"
    assert list(config["layout"]) == ["liquid"]
    assert config["layout"]["liquid"]["background_color"] == (33, 11, 45)
    assert config["layout"]["liquid"]["background_opacity"] == 0.2
    assert config["layout"]["liquid"]["offset_x"] == -4
    assert config["layout"]["liquid"]["offset_y"] == 6
    assert config["layout"]["liquid"]["font_color"] == (179, 0, 255)
    assert config["background"] == background_path
    assert len(frame) == 640 * 480 * 3
    assert frame[:3] == bytes((4, 3, 6))
    assert any(frame)


def test_lcd_statistics_color_accepts_optional_hash_and_rejects_invalid_values():
    assert _parse_lcd_color("B300FF") == (179, 0, 255)
    assert _parse_lcd_color("#B300FF") == (179, 0, 255)
    assert _parse_lcd_color(100713) == (16, 7, 19)
    with pytest.raises(ValueError, match="six-digit RGB"):
        _parse_lcd_color("purple")


@pytest.mark.parametrize("interval", [0, -1])
def test_lcd_statistics_shorthand_rejects_non_positive_intervals(interval):
    with pytest.raises(ValueError, match="interval must be greater than zero"):
        _load_lcd_stats_config("B300FF", interval)


def test_contrib_lcd_dashboard_examples_only_use_cooler_telemetry():
    examples = (
        "extra/contrib/asus_ryujin/example_layouts/ryujin_extreme_stats.json",
        "extra/contrib/asus_ryujin/example_layouts/ryujin_extreme_st4.json",
    )

    for path in examples:
        config = _load_lcd_stats_config(path, None)
        stats = [stat["stat"] for card in config["layout"].values() for stat in card["stats"]]
        assert set(stats) <= {
            "liquid_temperature",
            "pump_duty",
            "pump_speed",
            "pump_fan_duty",
            "pump_fan_speed",
        }


@pytest.mark.parametrize(
    "value,unit,max_digits,expected",
    [
        (35.2, "°C", 5, "35.2°C"),
        (1860, "rpm", 5, "1860rpm"),
        (12_430, "MHz", 5, "12430MHz"),
        (1_200_000, "", 5, "1.2M"),
        ("4.25", "GHz", 5, "4.25GHz"),
        ("N/A", "", 5, "N/A"),
    ],
)
def test_lcd_statistics_values_fit_their_digit_budget(value, unit, max_digits, expected):
    assert _format_lcd_value(value, unit, max_digits) == expected


def test_lcd_custom_stat_runs_an_argv_command_without_a_shell(monkeypatch):
    config = _load_lcd_stats_config(None, None)
    config["layout"] = {
        "custom": {
            "background_color": None,
            "font_color": None,
            "stats": [
                {
                    "stat": "custom",
                    "indicator": "TEST",
                    "command": ["metric-tool", "--value"],
                    "unit": "widgets",
                }
            ],
        }
    }
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="42\n")

    monkeypatch.setattr(asus_ryujin_lcd.subprocess, "run", run)
    custom_values = _read_lcd_custom_stats(config, 0)
    frame = _render_lcd_stats([], config, 0, 5, custom_values=custom_values)

    assert len(frame) == 640 * 480 * 3
    assert calls == [
        (
            ["metric-tool", "--value"],
            {
                "shell": False,
                "capture_output": True,
                "check": True,
                "text": True,
                "timeout": 2,
            },
        )
    ]


def test_lcd_custom_stat_rejects_a_shell_command_string(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {
                "layout": {
                    "custom": {
                        "stats": [
                            {"stat": "custom", "indicator": "TEST", "command": "echo 42"}
                        ]
                    }
                }
            }
        )
    )

    with pytest.raises(ValueError, match="non-empty list of strings"):
        _load_lcd_stats_config(path, None)


@pytest.fixture
def mock_ryujin():
    return _create_mock_ryujin(0x1988)


@pytest.fixture
def mock_ryujin3():
    return _create_mock_ryujin(0x1BCB)


@pytest.mark.parametrize("product_id", [0x1988, 0x1BCB, 0x1ADE, 0x1AA2])
def test_initialize(product_id):
    config = DEVICE_CONFIGS[product_id]
    device = _create_mock_ryujin(product_id)

    with device.connect():
        (firmware_status,) = device.initialize()
        assert firmware_status[1] == config["expected_firmware"]


@pytest.mark.parametrize("product_id", [0x1988, 0x1BCB, 0x1ADE, 0x1AA2])
def test_status(product_id):
    config = DEVICE_CONFIGS[product_id]
    device = _create_mock_ryujin(product_id)

    with device.connect():
        actual = device.get_status()

        expected = []
        for item in config["expected_status"]:
            name, value, unit = item
            if name == "Liquid temperature":
                expected.append((name, pytest.approx(value), unit))
            else:
                expected.append((name, value, unit))

        assert sorted(actual) == sorted(expected)


def test_set_fixed_speeds_ryujin2(mock_ryujin):
    with mock_ryujin.connect():
        mock_ryujin.set_fixed_speed(channel="pump", duty=10)
        assert mock_ryujin.device.requests[-1][2] == 0x00
        assert mock_ryujin.device.requests[-1][3] == 0x0A

        mock_ryujin.set_fixed_speed(channel="pump-fan", duty=20)
        assert mock_ryujin.device.requests[-1][2] == 0x00
        assert mock_ryujin.device.requests[-1][4] == 0x14

        mock_ryujin.set_fixed_speed(channel="external-fans", duty=30)
        assert mock_ryujin.device.requests[-1][4] == 0x4C

        mock_ryujin.set_fixed_speed(channel="fans", duty=40)
        assert mock_ryujin.device.requests[-2][4] == 0x28
        assert mock_ryujin.device.requests[-1][4] == 0x66


def test_set_fixed_speeds_ryujin3(mock_ryujin3):
    with mock_ryujin3.connect():
        mock_ryujin3.set_fixed_speed(channel="pump", duty=70)
        assert mock_ryujin3.device.requests[-1][2] == 0x01
        assert mock_ryujin3.device.requests[-1][3] == 0x46

        mock_ryujin3.set_fixed_speed(channel="pump-fan", duty=50)
        assert mock_ryujin3.device.requests[-1][2] == 0x01
        assert mock_ryujin3.device.requests[-1][4] == 0x32
