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
        self.target_path = os.getenv("APPDATA").replace("\\", "/") + "/KimoStudio/"
        self.saved = True
        self.header = None
        self.number_of_streams = None
        self.show()
    
    def openExcel(self):
        """Open the generated Excel file in the default application."""
        if os.path.exists(self.excel_path):
            os.startfile(self.excel_path.replace("/", "\\")) # Takees forever to open
            self.saved = False
        else:
            QMessageBox.warning(self, "File Not Found", "The Excel file does not exist. Please load a KFK file first.")

    def read_kfk(self):
        """Main function to read KFK file, decode it, and write to Excel."""
        # 1. Select the .kfk file
        self.file_path, _  = QFileDialog.getOpenFileName(self, "Open Kimo Data File", "", "Kimo Data File (*.kfk)")
        if not self.file_path: return
        # Unzip to default directory
        with zipfile.ZipFile(self.file_path, 'r') as zf:
            zf.extractall(path=self.target_path, pwd=self.password.encode())
        # Read Donnees from KFK
        with open(self.target_path + "/Campagnes/Donnees", "rb") as f:
            binary_content = f.read()
        
        # Separate and extract the header and data streams
        static = {}
        streams = []
        pos = 0
        while pos < len(binary_content):
            if binary_content[pos] == 0x80:
                length = struct.unpack('<I', binary_content[pos-4:pos])[0]
                block = binary_content[pos : pos + length]
                if len(streams) == 0:
                    self.header = binary_content[:pos-4] # Store the header for later use
                    static = processor.extract_static(self.header) # Extract static data from the header
                streams.append(processor.extract_data(block))
                pos = pos + length + 4
                continue
            pos += 1
        self.number_of_streams = len(streams)
        
        # Write to excel file
        if self.write_excel(static, streams):
            # Write filename to lineedit, show only filename without path
            self.ui.KimoFile.setText(os.path.basename(self.file_path))
            # Enable all the widgets
            self.ui.Save.setEnabled(True)
            self.ui.EditExcel.setEnabled(True)
            # Open Excel to show the result
            self.openExcel()
    
    def write_excel(self, static, streams):
        """Write the decoded data into an Excel file with proper formatting."""
        # 1. Open Excel file and select active worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = os.path.basename(self.file_path).strip('.kfk')

        # 2. Write headers
        ws["A1"] = "Serial No."
        ws["A2"] = "Software Version"
        ws["A3"] = "Start Date and Time"
        ws["A7"] = "Reading #"
        for i in range(self.number_of_streams):
            ws.cell(row=7, column=i+2, value=f"Channel {i+1}") # Start from column B (index 2)

        # 3. Write data
        ws["B1"] = static['serial']
        ws["B2"] = static['version']
        ws["B3"] = datetime.datetime.strptime(static['start_DTime'], "%d/%m/%Y %H:%M:%S")

        for i in range(max([len(x) for x in streams])):
            ws.cell(row=i+8, column=1, value=i+1)
            for j in range(self.number_of_streams):
                ws.cell(row=i+8, column=j+2, value=streams[j][i]) # Start from row 8 (index 7) and column B (index 2)

        # 4. Formats and styling
        # Auto-adjust column widths
        for column_cells in ws.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 2

        # Align cells
        ws["B3"].alignment = openpyxl.styles.Alignment(horizontal="left")

        # Auto-format headers
        # Select range A7:len(readings)+1 and make them bold with gray background
        for row in ws.iter_rows(min_row=7, max_row=7, min_col=1, max_col=1+self.number_of_streams):
            for cell in row:
                cell.font = openpyxl.styles.Font(bold=True)
                cell.fill = openpyxl.styles.PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

        # 5. Save the workbook
        self.excel_path = self.target_path + "/" + os.path.basename(self.file_path).replace('.kfk', '.xlsx')
        wb.save(self.excel_path) 
        return True
        
    def write_kfk(self):
        """Main function to write KFK file based on edited Excel data."""
        # 1. Create a save file dialog to get output kfk path
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Kimo Data File", self.file_path, "Kimo Data File (*.kfk)")
        if not save_path:
            return

        # 2. Read Excel Data
        df = pd.read_excel(self.excel_path, header=None)
        static_data = { # Read static data
            'serial': df.iloc[0, 1],
            'version': df.iloc[1, 1],
            'start_DTime': df.iloc[2, 1].strftime("%d/%m/%Y %H:%M:%S") # Convert datetime to string
        }
        # Read channel data starting from row 8 (index 7) and column 2 (index 1)
        new_streams = [df.iloc[7:, i+1].tolist() for i in range(self.number_of_streams)]
        
        # 3. Generate New static header and Binary Stream
        new_data = processor.compress_static(static_data, self.header)
        new_streams = [processor.compress_data(stream) for stream in new_streams]
        for stream in new_streams:
            payload_length = len(stream)
            new_data += struct.pack('<I', payload_length)
            new_data += stream
        
        # 4. Write to a new Donnees file
        campagnes = self.target_path + "Campagnes/"
        with open(campagnes + "Donnees", "wb") as f:
            f.write(new_data)

        # 5. Package into KFK (Assuming config/signature are in current dir)
        files_list = [campagnes + "Donnees", campagnes + "Configuration", campagnes + "Signatures"]
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
        self.hide()
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