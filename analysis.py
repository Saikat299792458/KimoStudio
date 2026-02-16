import struct
class processor:
    def __init__(self):
        pass
    
    def decode_kimo_stream(data):
        """Universal decoder handling 2-byte magnitudes and sign flags."""
        anchor_idx = -1
        # Search for 80 [XX] [YY] [00 or 80]
        for i in range(len(data) - 4):
            if data[i] == 0x80 and (data[i+3] == 0x00 or data[i+3] == 0x80):
                anchor_idx = i
                break
        if anchor_idx == -1: return None

        # Extract 2-byte magnitude and sign flag
        magnitude = struct.unpack('<H', data[anchor_idx+1:anchor_idx+3])[0]
        is_negative = (data[anchor_idx+3] == 0x80)
        
        current_val = -(magnitude / 10.0) if is_negative else (magnitude / 10.0)
        results = [round(current_val, 1)]

        # Process Delta Stream
        cursor = anchor_idx + 4
        while cursor < len(data):
            byte = data[cursor]
            cursor += 1
            if byte == 0x00: continue
            
            if 0x01 <= byte <= 0x7F: # RLE (Repeat)
                for _ in range(byte): results.append(round(current_val, 1))
            elif 0x81 <= byte <= 0xBF: # Increase
                current_val += (byte - 0x80) / 10.0
                results.append(round(current_val, 1))
            elif 0xC1 <= byte <= 0xFF: # Decrease
                current_val -= (byte - 0xC0) / 10.0
                results.append(round(current_val, 1))
        return results

    def encode_kimo_stream(temps):
        """Universal encoder that correctly formats the 4-byte anchor."""
        first_temp = temps[0]
        magnitude = int(round(abs(first_temp) * 10))
        sign_flag = 0x80 if first_temp < 0 else 0x00
        
        # Build Anchor: 0x80 + 2-byte Mag + Sign
        stream = bytearray([0x80]) + struct.pack('<H', magnitude) + bytearray([sign_flag])
        
        current_temp = first_temp
        i = 1
        while i < len(temps):
            target = temps[i]
            # CASE A: Run-Length Encoding (Stability)
            # Check how many subsequent values are identical
            repeat_count = 0
            while (i + repeat_count < len(temps) and 
                temps[i + repeat_count] == current_temp and 
                repeat_count < 127):
                repeat_count += 1
            
            if repeat_count > 0:
                stream.append(repeat_count)
                i += repeat_count
                continue
            # CASE B: Delta Encoding
            diff = int(round((target - current_temp) * 10))
            if diff > 0: stream.append(0x80 + diff)
            elif diff < 0: stream.append(0xC0 + abs(diff))
            current_temp = target
            i += 1
        return stream