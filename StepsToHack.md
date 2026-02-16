1. Run KILOG2015 Software in your computer.
2. Using the process hacker select Kilog2015.exe
3. right click and go to properties.
4. Click on the memory tab and go to options
5. Click on Strings and click OK
6. Click on Filter and select contains (Case insenstive)
7. Search for Password. One entry should contain something like following:
0x55c462c (330): Data Source =C:\Users\Public\Documents\KIMO Instruments\Kilog 2015\Bases\KILOG.sdf; Max Database Size = 4000; Password = '@MoKa_2433'; Persist Security Info = False;

8. The kfk file is a zip file with legacy zipcrypto encryption. Extract the zip file with the Password. It contains 3 files. Configuration, Signatures, Donnees.
9. Open the Binary Donnees file with a hex editor.
9. The file contains some header information separated by padding 0x00 Bytes, such as session name, recording time, measuring time etc. Since we're interested in editing the file, not creating kfk files, we can keep these header information as is. The raw data is bundled around the end of the file separated from the header information by a four byte separator.
10. The four byte separator looks like this: 80 KL MN PQ. 
The Byte PQ can be either 00 (for positive first value) or 80 (for negative first value). 
The Bytes KL MN are used to record the first value of the session multiplied by 10 in Little Endian format. For example if the bytes are 5E 01, in little endian it converts to 350. Dividing it by 10 gives the first value of the temperature which is 35.0. 
11. The consecutive values in the Donnees file are the delta (Differential data) from the previous value. If the delta is positive, it is multiplied by 10 and added to 0x80. If the delta is negative, it is multiplied by 10 and added to 0xC0. And if the temperature doesn't change, the number of times we get the same temperature is counted and added to 0x00. For example consider the following data and byte stream:

80 98 00 80 81 06 c1 81 03

-15.2 -15.1 -15.1 -15.1 -15.1 -15.1 -15.1 -15.1 -15.2 -15.1 -15.1 -15.1 -15.1

12. Note that, some logger data may contain multiple temperature channels and, some loggers are capable of recording humidity data too. For now I need single channel temperature data, further analysis will be required to edit multi channel data in the future.