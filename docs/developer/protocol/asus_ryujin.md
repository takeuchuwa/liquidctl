# ASUS Ryujin II liquid cooler protocol

The data of all usb packets is 65 bytes long, prefixed with `0xEC`.


## Ryujin III Extreme LCD

The Ryujin III Extreme (USB ID `0b05:1bcb`) exposes its LCD on a separate bulk
USB interface.  The cooler control interface is HID, while the LCD pixel data
is written to bulk OUT endpoint `0x02`.

The display is 640×480 pixels in packed RGB888 format (921,600 bytes per
frame).  Before a frame upload, perform the following HID operations:

1. Query LCD state: `EC D0`; the reply is headed by `EC 50`.
   - byte 4 is the panel ID;
   - byte 5 is the current display mode;
   - bytes 6–7 are mode arguments.
2. Write raw framebuffer mode `EC 51 20 <reply byte 6> <reply byte 7>`.
   Reapply this command even when the reported mode is already `0x20`, to
   reset display state left by an earlier raw-frame session.
3. Announce the byte length with `EC 7F 03 <u32le length>`.
4. Write the RGB888 frame to bulk endpoint `0x02`.

Frame data is sent in ordinary top-to-bottom, left-to-right RGB888 order.

### Firmware display modes

The modes below were reverse engineered from USB captures of the vendor
software (Armoury Crate) and are handled by the cooler itself; the host does
not need to keep sending data.  Every command is acknowledged with a report
headed by `EC` and the command byte, except where a different reply header is
given.  Some operations are also followed by an unsolicited notification
report prefixed with `EE` instead of `EC`.

Display mode, `EC 51 <mode> [<arguments>]`:

| Mode | Arguments | Meaning |
| --- | --- | --- |
| `00` | | display off |
| `11` | `01` | image stored in the cooler |
| `14` | `01` | video stored in the cooler |
| `1F` | | text layout (label and value) |
| `20` | bytes 6–7 of the `EC D0` reply | raw framebuffer, see above |

Before switching to a stored image, video or the text layout the vendor
software also writes `EC 5D 00 01 <code> ...` (`11 01 00 00 00 05` for an
image, `14 01 00 00 00 01` for a video, `21 00 01 00 00 05` for text).  The
meaning of the individual bytes is unknown.

Display settings:

- Read: `EC DC`, reply headed by `EC 5C`; bytes 5, 9 and 15 hold the
  brightness (0–100) and bytes 10 and 16 hold `0x14`.
- Write: `EC 5C 01 00 00 <b> 00 00 00 <b> 14 00 00 00 00 <b> 14`.  The vendor
  software always reads the settings first.  The setting survives a reboot of
  the cooler.

Text layout:

- `EC 5F 00 00 <label, 18 bytes, zero padded> <value, UTF-8>` sets the label
  and the value, e.g. `Liquid` and `34.0℃`.  The vendor software resends it
  about once per second.
- `EC 5E 00 00 00 00 01 01 FF FF FF 00 FF FF FF 01 FF FF FF 00 FF FF FF 01 FF FF FF 00 FF FF FF`
  precedes the mode change; it appears to carry the text colours.

Clock: `EC 11 C6 <month> <day> <weekday> 00 <hours> <minutes> <seconds> 01`,
all fields in BCD.  Sent by the vendor software before every mode change; not
required for the modes above.

Storing a file (a 640×480 baseline JPEG, or a 640×480 Motion JPEG AVI):

1. `EC 71 01 01`, followed by notification `EE 12`.
2. `EC F1`; the reply is headed by `EC 71` and appears to describe the storage
   (total and free space).  Its fields are not understood.
3. `EC 72 01 01` for an image or `EC 72 01` for a video.
4. `EC 73 01` opens the transfer, followed by notification `EE 13 <status> 01`.
   Status `00` means the transfer is open.  Status `10` means it was refused;
   the following `EC 7F` is then answered with `EC 7F 02` and data blocks are
   never acknowledged.  A refused transfer leaves the stored file untouched
   and must still be closed (step 8).
5. `EC 7F 02 <u24le file size>`; the reply `EC 7F 00 00 10` gives the block
   size (`0x1000`).  Note that the raw framebuffer mode uses `EC 7F 03` with a
   32-bit length instead.
6. Wait before sending data.  The vendor software waits about 0.5 s; without
   a pause the first block of a 400 kB file was never acknowledged.
7. Write the file to bulk endpoint `0x02` in 4096-byte blocks, the last one
   padded with zeros.  Each block is acknowledged with notification
   `EE 14 00 00 <n>`, after which the next block may be sent immediately.
8. `EC 73 FF` closes the transfer, followed by notification `EE 13 00 FF`.

**`EC 73 FF` must only be sent while a transfer is open.**  Sent on its own
it is not acknowledged and the cooler reboots (the device disconnects from
USB and its fans briefly run at full speed).  A transfer interrupted after
step 4 must still be closed.

Stored files are lost when the cooler loses power but survive a warm reboot
of the computer.

Behaviour observed on firmware `AURJ3-S5F9-0104`:

- **The stored video cannot be replaced while it is playing.**  The transfer
  is refused with status `10`.  Switch to another mode first (`EC 51 00` is
  enough); the file is released a few tenths of a second later, so the open
  may need to be retried.  Images can be replaced at any time.
- **The video player only accepts the AVI layout written by FFmpeg**, which
  is what the vendor software uploads: an `hdrl` list of 4588 bytes with the
  OpenDML padding chunks, a `LIST INFO`, a 1016-byte `JUNK` chunk, and the
  `movi` list starting at offset `0x1622`.  A minimal but valid AVI (headers
  directly followed by `movi`) hangs the player: the display mode reported by
  `EC D0` stops changing and every later video transfer is refused until the
  cooler is power cycled.
- The same hang happens when a video transfer is opened and closed without
  sending any data and the (now empty) video is then selected.
- Mode changes are reflected by `EC D0` after 0.1–0.2 s.  Checking it after
  selecting a stored video detects a hung player.


## Generic Operations

### Get firmware info

- Request:
    - Header: `0xEC 0x82`
- Response:
    - Header: `0xEC 0x02`
    - Data:
        - Byte 4-18: Firmware version (ascii)


## Cooling Operations

### Get cooling info

- Request:
    - Header: `0xEC 0x99`
- Response:
    - Header: `0xEC 0x19`
    - Data:
        - Byte 4: Liquid temperature (integer digits)
        - Byte 5: Liquid temperature (decimal digit)
        - Byte 6-7: Pump rpm (little endian)
        - Byte 8-9: Embedded Micro Fan rpm (little endian)

### Get duties of pump and of embedded micro fan

- Request:
    - Header: `0xEC 0x9A`
- Response:
    - Header: `0xEC 0x1A`
    - Data:
        - Byte 5: Pump duty % from 0x00 to 0x64
        - Byte 6: Embedded Micro Fan duty % from 0x00 to 0x64

### Get fan speed of AIO fan controller

- Request:
    - Header: `0xEC 0xA0`
- Response:
    - Header: `0xEC 0x20`
    - Data:
        - Byte 4-5: Fan 4 rpm (little endian)
        - Byte 6-7: Fan 1 rpm (little endian)
        - Byte 8-9: Fan 2 rpm (little endian)
        - Byte 10-11: Fan 3 rpm (little endian)

### Get duty of AIO fan controller

- Request:
    - Header: `0xEC 0xA1`
- Response:
    - Header: `0xEC 0x21`
    - Data:
        - Byte 5: AIO fan controller duty from 0x00 to 0xFF

### Set duties of pump and of embedded micro fan

- Request:
    - Header: `0xEC 0x1A`
    - Data:
        - Byte 4: Pump duty % from 0x00 to 0x64
        - Byte 5: Embedded Micro Fan duty % from 0x00 to 0x64
- Response:
    - Header: `0xEC 0x1A`

### Set duty of AIO fan controller

- Request:
    - Header: `0xEC 0x21`
    - Data:
        - Byte 5: AIO fan controller duty from 0x00 to 0xFF
- Response:
    - Header: `0xEC 0x21`


## Unknown

- Request:
    - Header: `0xEC 0xAF`
- Response:
    - Header: `0xEC 0x2F`
        - Byte 4-17: ?
