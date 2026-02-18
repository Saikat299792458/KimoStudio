import struct
import sys
import zipfile
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QFileDialog, QMessageBox)
import openpyxl
import pandas as pd
import pyminizip
from analysis import processor
import shutil
from bareMinimum_ui import Ui_MainWindow

class MyWindow(QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setFixedSize(self.width(), self.height())
        self.setWindowTitle("KIMO Studio - KFK Editor")
        self.ui.OpenKimo.clicked.connect(self.read_kfk)
        self.ui.OpenExcel.clicked.connect(self.browse_file)
        self.ui.Save.clicked.connect(self.write_kfk)
        self.ui.EditExcel.clicked.connect(lambda: os.startfile(self.output_file.replace("/", "\\")))
        self.ui.KimoFile.setReadOnly(True)
        self.ui.ExcelFile.setReadOnly(True)
        self.ui.ExcelFile.setEnabled(False)
        self.ui.OpenExcel.setEnabled(False)
        self.ui.Save.setEnabled(False)
        self.ui.EditExcel.setEnabled(False)
        self.password = "@MoKa_2433"  # Default password
        self.show()
    
    def browse_file(self):
        # get name from lineedit
        name = self.ui.ExcelFile.text().strip()
        self.output_file, _ = QFileDialog.getOpenFileName(self, "Open Excel File", name, "Excel Files (*.xlsx)")
        if not self.output_file:
            return
        self.ui.ExcelFile.setText(os.path.basename(self.output_file))

    def read_kfk(self):
        # 1. Select the .kfk file
        self.file_path, _  = QFileDialog.getOpenFileName(self, "Open Kimo Data File", "", "Kimo Data File (*.kfk)")
        if not self.file_path: return
        self.target_path = os.getenv("APPDATA").replace("\\", "/")
        with zipfile.ZipFile(self.file_path, 'r') as zf:
            # Extract to $env:appdata
            zf.extractall(path=self.target_path, pwd=self.password.encode())

        # Read Donnees from KFK
        self.target_path += "/Campagnes/"
        with open(self.target_path + "Donnees", "rb") as f:
            self.binary_content = f.read()
        # Decode
        readings = processor.decode_kimo_stream(self.binary_content)
        # Write to excel file
        if self.write_excel(readings, self.file_path.split('/')[-1].strip('.kfk')):
            # Write filename to lineedit
            # show only filename without path
            self.ui.KimoFile.setText(os.path.basename(self.file_path))
            self.ui.ExcelFile.setText(os.path.basename(self.output_file))
            # Enable all the widgets
            self.ui.OpenExcel.setEnabled(True)
            self.ui.Save.setEnabled(True)
            self.ui.ExcelFile.setEnabled(True)
            self.ui.EditExcel.setEnabled(True)
            # Open Excel to show the result
            os.startfile(self.output_file.replace("/", "\\"))
    
    def write_excel(self, readings, name):
        # Select an excel filename to save using windows default save as dialog
        self.output_file, _ = QFileDialog.getSaveFileName(self, "Save Excel File", f"{name}.xlsx", "Excel Files (*.xlsx)")
        if not self.output_file:
            return False

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = name

        # Write headers
        ws["A1"] = "Reading #"
        ws["B1"] = "Temp (°C)"

        # Write data
        for i, val in enumerate(readings, start=2):
            ws[f"A{i}"] = i - 1
            ws[f"B{i}"] = val

        # Auto-format headers
        header_range = ws["A1:B1"]
        for cell in header_range[0]:
            cell.font = openpyxl.styles.Font(bold=True)
            cell.fill = openpyxl.styles.PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")

        # Save the workbook
        wb.save(self.output_file)
        return True
        

    def write_kfk(self):
        # Create a save file dialog to get output kfk path
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Kimo Data File", self.file_path, "Kimo Data File (*.kfk)")
        if not save_path:
            return
        excel_path = self.output_file
        # 1. Read Excel Data
        df = pd.read_excel(excel_path)
        # Assume temperatures are in the first column
        new_temps = df.iloc[:, 1].tolist() 
        
        # Find the anchor to know where the header ends
        anchor_idx = -1
        # Search for 80 [XX] [YY] [00 or 80]
        for i in range(len(self.binary_content) - 4):
            if self.binary_content[i] == 0x80 and (self.binary_content[i+3] == 0x00 or self.binary_content[i+3] == 0x80):
                anchor_idx = i
                break
        
        header = self.binary_content[:anchor_idx - 4] # skip the 4 bytes indicating the number of bytes in the data

        # 3. Generate New Binary Stream
        new_stream = processor.encode_kimo_stream(new_temps)

        # 4. Pack the number of bytes in the data
        payload_length = len(new_stream)
        length_header = struct.pack('<I', payload_length)
        
        # 4. Save the new Donnees file locally
        with open(self.target_path + "Donnees", "wb") as f:
            f.write(header + length_header + new_stream)

        # 5. Package into KFK (Assuming config/signature are in current dir)
        files_list = [self.target_path + "Donnees", self.target_path + "Configuration", self.target_path + "Signatures"]
        prefix_list = ['Campagnes/', 'Campagnes/', 'Campagnes/']

        pyminizip.compress_multiple(files_list, prefix_list, save_path, self.password, 5)
        QMessageBox.information(self, "Success", f"Successfully generated {save_path}")
    
    # handle close event to clean up extracted files
    def closeEvent(self, event):
        # Force Delete Campagnes folder if exists recursively
        try:
            shutil.rmtree(self.target_path)
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyWindow()
    sys.exit(app.exec_())