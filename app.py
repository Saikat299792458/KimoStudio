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
from evenMoreBare import Ui_MainWindow
import datetime
import psutil

class MyWindow(QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setFixedSize(self.width(), self.height())
        self.setWindowTitle("KIMO Studio - KFK Editor")
        self.ui.OpenKimo.clicked.connect(self.read_kfk)
        self.ui.Save.clicked.connect(self.write_kfk)
        self.ui.EditExcel.clicked.connect(self.openExcel)
        self.ui.KimoFile.setReadOnly(True)
        self.ui.Save.setEnabled(False)
        self.ui.EditExcel.setEnabled(False)
        self.password = "@MoKa_2433"  # Default password
        self.saved = True
        self.show()
    
    def openExcel(self):
        """Open the generated Excel file in the default application."""
        if os.path.exists(self.output_file):
            os.startfile(self.output_file.replace("/", "\\")) # Takees forever to open
            self.saved = False
        else:
            QMessageBox.warning(self, "File Not Found", "The Excel file does not exist. Please load a KFK file first.")


    def read_kfk(self):
        """Main function to read KFK file, decode it, and write to Excel."""
        # 1. Select the .kfk file
        self.file_path, _  = QFileDialog.getOpenFileName(self, "Open Kimo Data File", "", "Kimo Data File (*.kfk)")
        if not self.file_path: return
        self.target_path = os.getenv("APPDATA").replace("\\", "/")
        with zipfile.ZipFile(self.file_path, 'r') as zf:
            # Extract to $env:appdata
            zf.extractall(path=self.target_path, pwd=self.password.encode())

        # Set default excel file location
        self.output_file = self.target_path + "/" + os.path.basename(self.file_path).replace('.kfk', '.xlsx')
        # Read Donnees from KFK
        self.target_path += "/Campagnes/"
        with open(self.target_path + "Donnees", "rb") as f:
            self.binary_content = f.read()
        # Decode
        static, readings = processor.decode_kimo_stream(self.binary_content)
        print(readings)
        # Write to excel file
        if self.write_excel(static, readings, os.path.basename(self.file_path).strip('.kfk')):
            # Write filename to lineedit
            # show only filename without path
            self.ui.KimoFile.setText(os.path.basename(self.file_path))
            # Enable all the widgets
            self.ui.Save.setEnabled(True)
            self.ui.EditExcel.setEnabled(True)
            # Open Excel to show the result
            self.openExcel()
    
    def write_excel(self, static, readings, title):
        """Write the decoded data into an Excel file with proper formatting."""
        # 1. Open Excel file and select active worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title

        # 2. Write headers
        ws["A1"] = "Serial No."
        ws["A2"] = "Software Version"
        ws["A3"] = "Start Date and Time"
        ws["A7"] = "Reading #"
        for i in range(len(readings)):
            ws.cell(row=7, column=i+2, value=f"Channel {i+1}") # Start from column B (index 2)

        # 3. Write data
        ws["B1"] = static['serial']
        ws["B2"] = static['version']
        ws["B3"] = datetime.datetime.strptime(static['start_DTime'], "%d/%m/%Y %H:%M:%S")
        print(len(readings), len(readings[0]))
        for i in range(len(readings[0])):
            for j in range(len(readings)):
                ws.cell(row=i+8, column=j+2, value=readings[j][i]) # Start from row 8 (index 7) and column B (index 2)

        # 4. Formats and styling
        # Auto-adjust column widths
        for column_cells in ws.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 2

        # Align cells
        ws["B3"].alignment = openpyxl.styles.Alignment(horizontal="left")

        # Auto-format headers
        # Select range A7:len(readings)+1 and make them bold with gray background
        for cell in ws["A7:A" + str(7 + len(readings))]:
            cell[0].font = openpyxl.styles.Font(bold=True)
            cell[0].fill = openpyxl.styles.PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

        # 5. Save the workbook
        wb.save(self.output_file) 
        return True
        

    def write_kfk(self):
        """Main function to write KFK file based on edited Excel data."""
        # 1. Create a save file dialog to get output kfk path
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Kimo Data File", self.file_path, "Kimo Data File (*.kfk)")
        if not save_path:
            return
        excel_path = self.output_file

        # 2. Read Excel Data
        df = pd.read_excel(excel_path, header=None)
        static_data = { # Read static data
            'serial': df.iloc[0, 1],
            'version': df.iloc[1, 1],
            'start_DTime': df.iloc[2, 1].strftime("%d/%m/%Y %H:%M:%S") # Convert datetime to string
        }

        new_temps = df.iloc[7:, 1].tolist() # Read temperature data starting from row 8 (index 7)

        # 3. Read Original Binary Content to get the header and anchor position
        anchor_idx = -1 # Find the anchor to know where the header ends
        for i in range(len(self.binary_content) - 4): # Search for 80 [XX] [YY] [00 or 80]
            if self.binary_content[i] == 0x80 and (self.binary_content[i+3] == 0x00 or self.binary_content[i+3] == 0x80):
                anchor_idx = i
                break
        
        header = self.binary_content[:anchor_idx - 4] # skip the 4 bytes indicating the number of bytes in the data

        # 4. Generate New static header and Binary Stream
        new_header = processor.write_header(static_data, header)
        new_stream = processor.encode_kimo_stream(new_temps)

        # 5. Pack the number of bytes in the data
        payload_length = len(new_stream)
        length_header = struct.pack('<I', payload_length)
        
        # 6. Save the new Donnees file locally
        with open(self.target_path + "Donnees", "wb") as f:
            f.write(new_header + length_header + new_stream)

        # 7. Package into KFK (Assuming config/signature are in current dir)
        files_list = [self.target_path + "Donnees", self.target_path + "Configuration", self.target_path + "Signatures"]
        prefix_list = ['Campagnes/', 'Campagnes/', 'Campagnes/']

        pyminizip.compress_multiple(files_list, prefix_list, save_path, self.password, 5)
        self.saved = True
        QMessageBox.information(self, "Success", f"Successfully generated {save_path}")
    

    def terminate_excel_with_file(self, file_path):
        """Terminate any process that has file_path open (e.g., Excel)."""
        for proc in psutil.process_iter(['pid', 'name', 'open_files']):
            open_files = proc.info.get('open_files')
            if not open_files:
                continue
            for f in open_files:
                if os.path.normcase(os.path.abspath(file_path)) == os.path.normcase(os.path.abspath(f.path)):
                    proc.terminate()
                    break

    def closeEvent(self, event):
        """Cleanup extracted files on close."""
        if not self.saved:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to exit without saving?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
        try:
            shutil.rmtree(self.target_path)
            self.terminate_excel_with_file(self.output_file)
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyWindow()
    sys.exit(app.exec_())