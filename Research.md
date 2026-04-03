# Extraction of KIMO Data File
1. Run **KILOG2015** Software in your computer.
2. Using the **Process Hacker** app, select **Kilog2015.exe**.
3. Right click and go to properties.
4. Click on the memory tab and go to options.
5. Click on Strings and click OK.
6. Click on Filter and select contains (Case insenstive).
7. Search for **"Password"**. One entry should contain something like following:
`0x55c462c (330): Data Source =C:\Users\Public\Documents\KIMO Instruments\Kilog 2015\Bases\KILOG.sdf; Max Database Size = 4000; Password = '@MoKa_2433'; Persist Security Info = False;`

8. The kfk file is a zip file with legacy zipcrypto encryption. Extract the zip file with the Password. It contains 3 files. **Configuration, Signatures, and Donnees**.
9. Open the Binary **Donnees** file with a hex editor. It has the following structure:

# Kimo Donnees File Specification

## 1. Important Header & Session Related Metadata

| Anchor | Offset | Size | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0x00 | 0x06 | 8 | ASCII | Hardware model (e.g., `aKH220-O`). |
| 0x00 | 0x11 | 2 | ASCII | first section of Serial Number. i.e., 2K. |
| 0x00 | 0x13 | 2 | uint | Second section of Serial Number with an optional leading zero. i.e., 15. |
| 0x00 | 0x15 | 1 | uint | Third section of Serial Number with an optional leading zero. i.e., 09. |
| 0x00 | 0x16 | 3 | uint | Fourth section of Serial Number (5 digits) with optional leading zeroes. i.e., 42145. |
| 0x00 | 0x19 | 3 | float | Software Version No. i.e., 1.20. |
| 0x63 | 0x00 | Variable | ASCII | Dataset Name. Ends with a nullbyte (NB_ID) |
| NB_ID | 0x00 | Variable | ASCII | Comments. Ends with a nullbyte (NB_CMT) |

## 2. Temporal Metadata (Relative to Comment Null Byte)
| Anchor | Offset | Size | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| NB_CMT | 0x01 | 4 | uint | Interval in seconds. |
| NB_CMT +20 | 0x00 | 1 | uint | Date - Day. |
| NB_CMT +20 | 0x01 | 1 | uint | Date - Month. |
| NB_CMT +20 | 0x02 | 2 | uint | Date - Year. |
| NB_CMT +20 | 0x04 | 1 | uint | Date - Hour. |
| NB_CMT +20 | 0x05 | 1 | uint | Date - Minute. |
| NB_CMT +20 | 0x06 | 1 | uint | Date - Second. |

## 3. Data Channel Structure
Following the header metadata, each measurement channel (Temperature, RH, etc.) is stored as an independent block.

### Channel Preamble
Each channel starts with a **4-byte Little-Endian Integer** indicating the total number of records (data points) for that specific channel.

### The Delta-Encoded Stream
The actual measurement data begins immediately after the count with the marker byte `0x80`.

1.  **Initial Base Value (2 Bytes):** The first reading after `0x80`. Stored as a 2-byte Little-Endian integer. 
    * *Formula:* `Value = Integer / 10`
2. **Sign Byte:** After the base value, 1 byte contains the sign of the first value. `0x00` for **positive** and `0x80` for **negative**.
2.  **Delta Bytes:** Subsequent bytes describe the change relative to the *previous* value:
    * **Positive Delta:** `0x81` to `0xBF` $\rightarrow$ Add `(Byte - 0x80) * 0.1` to the decimal value.
    * **Negative Delta:** `0xC1` to `0xFF` $\rightarrow$ Subtract `(Byte - 0xC0) * 0.1` to the decimal value.
    * **Repeat Count:** `0x01` to `0x7F` $\rightarrow$ The previous value remains unchanged for $N$ records.



## 4. Multi-Channel Logic
Channels are appended sequentially in the file. To process a file with multiple sensors:
1. Locate the count for Channel 1.
2. Decode the delta stream for Channel 1 until the record count is met.
3. The very next byte will be the start of the 4-byte count for Channel 2.

> All the data are separated by padding 0x00 Bytes.