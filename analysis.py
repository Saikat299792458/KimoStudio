import struct
class processor:
    def __init__(self):
        pass

    def decode_kimo_stream(data):
        """Universal decoder handling 2-byte magnitudes and sign flags."""
        # Find serial number and software version
        static = {}
        # convert 17 and 18 th bytes to ascii
        serial = data[17:19].decode('ascii') # 2K
        serial += " "
        # Convert the 19th and 20th bytes to an two digit integer with leading zeros if necessary and append to serial
        serial += f"{(struct.unpack('<H', data[19:21])[0]):02d}" # 17
        serial += "."
        # Convert the 21st byte to an two digit integer with leading zeros if necessary and append to serial
        serial += f"{(data[21]):02d}" # 09
        serial += "."
        # Convert the next 3 bytes to an 5 digit integer with leading zeros if necessary and append to serial
        serial += f"{(int.from_bytes(data[22:25], byteorder='little')):05d}"
        static['serial'] = serial

        # Convert the next 3 bytes to float with 1 decimal place and store as software version
        version = struct.unpack('<f', data[25:29])[0]
        static['version'] = f"{version:.2f}"
        
        # Find Start Date and Time dynamically
        start_idx = 63
        # Find the null byte that ends the first string (The ID)
        null1_idx = data.find(b'\x00', start_idx)
        # Find the null byte that ends the second string (The Comment)
        null2_idx = data.find(b'\x00', null1_idx + 1)

        # The Date block is exactly 20 bytes after the second null byte
        date_pos = null2_idx + 20
        start_DTime = f"{(data[date_pos]):02d}" # Day
        start_DTime += f"/{(data[date_pos + 1]):02d}" # Month
        year = struct.unpack('<H', data[date_pos + 2:date_pos + 4])[0]
        start_DTime += f"/{year:04d}" # Year
        start_DTime += f" {data[date_pos + 4]:02d}:{data[date_pos + 5]:02d}:{data[date_pos + 6]:02d}" # Time
        static['start_DTime'] = start_DTime

        # Extract readings...
        results = []
        channel = -1
        current_val = 0.0
        i = 0
        # Search for 80 [XX] [YY] [00 or 80]
        while i < len(data):
            if len(data) - i >= 4 and data[i] == 0x80 and (data[i+3] == 0x00 or data[i+3] == 0x80):
                results.append([])
                channel += 1
                # Extract 2-byte magnitude and sign flag
                magnitude = struct.unpack('<H', data[i+1:i+3])[0]
                is_negative = (data[i+3] == 0x80)
                
                current_val = -(magnitude / 10.0) if is_negative else (magnitude / 10.0)
                results[channel] = [round(current_val, 1)]
                i += 4
                continue
            
            if channel >= 0:
                byte = data[i]
                if byte == 0x00 or byte == 0x80: 
                    i += 1
                    continue

                if 0x01 <= byte <= 0x7F: # RLE (Repeat)
                    for _ in range(byte): results[channel].append(round(current_val, 1))
                elif 0x81 <= byte <= 0xBF: # Increase
                    current_val += (byte - 0x80) / 10.0
                    results[channel].append(round(current_val, 1))
                elif 0xC1 <= byte <= 0xFF: # Decrease
                    current_val -= (byte - 0xC0) / 10.0
                    results[channel].append(round(current_val, 1))
            i += 1
        return static, results
    
    def write_header(static_data, original_header):
        """Writes a new header based on the original, replacing only the static fields."""
        # Start with the original header as a bytearray for mutability
        new_header = bytearray(original_header)
        
        # Update Serial Number (Bytes 17-24)
        serial_parts = static_data['serial'].split(' ')
        serial_main = serial_parts[0] # e.g. "2K"
        serial_sub = serial_parts[1] # e.g. "17.09.00001"
        
        # Write the first part of the serial (e.g. "2K")
        new_header[17:19] = serial_main.encode('ascii')
        
        # Extract and write the numeric parts of the serial
        sub_parts = serial_sub.split('.')
        new_header[19:21] = struct.pack('<H', int(sub_parts[0])) # 17
        new_header[21] = int(sub_parts[1]) # 09
        new_header[22:25] = int(sub_parts[2]).to_bytes(3, byteorder='little') # 00001
        
        # Update Software Version (Bytes 25-28)
        version_float = float(static_data['version'])
        new_header[25:29] = struct.pack('<f', version_float) # might have serious problem, use database instead
        
        # Update Interval (Dynamically find position after second null byte)
        start_idx = 63
        null1_idx = new_header.find(b'\x00', start_idx)
        null2_idx = new_header.find(b'\x00', null1_idx + 1)
        
        # Update Start Date and Time (20 bytes after index of second null byte)
        date_pos = null2_idx + 20
        dt_parts = static_data['start_DTime'].split(' ')
        date_part = dt_parts[0]
        time_part = dt_parts[1]
        
        day, month, year = map(int, date_part.split('/'))
        hour, minute, second = map(int, time_part.split(':'))
        
        new_header[date_pos] = day
        new_header[date_pos + 1] = month
        new_header[date_pos + 2:date_pos + 4] = struct.pack('<H', year)
        new_header[date_pos + 4] = hour
        new_header[date_pos + 5] = minute
        new_header[date_pos + 6] = second
        return new_header

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