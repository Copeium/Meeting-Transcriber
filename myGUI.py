import os
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QHBoxLayout, QLabel, QGridLayout, QPlainTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QIcon

import sounddevice as sd
import myStream
from pywhispercpp.model import Segment
import pywhispercpp.utils as utils
import logging
from datetime import datetime
logging.basicConfig(level=logging.INFO)

STYLESHEET = """
    QHeaderView::section {
        background-color: #e8e8e8;
    }
    QTableWidget::item {
        padding: 8px;
    }
    QPlainTextEdit {
        background-color: #1e1e1e;
        color: #ffffff;
        padding: 8px;
    }
"""


class TranscriberUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcriber by Faith Lawrence Escano")
        self.setGeometry(200, 200, 1000, 800)
        self.setStyleSheet(STYLESHEET)
        def resource_path(relative_path):
            if hasattr(sys, "_MEIPASS"):
                return os.path.join(sys._MEIPASS, relative_path)
            return os.path.join(os.path.abspath("."), relative_path)

        self.setWindowIcon(QIcon(resource_path("icon.ico")))

        self.input_dropdown = None # Holds the input device
        self.model_dropdown = None # Holds the model selection
        self.status_label = None # Status label at the bottom
        self.table = None # Table to show transcriptions
        self.lastTime = None # Last time a segment was added

        self.segments = [] # Holds the segments for export
        self.streamer = None # Will hold the streaming object

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Grid layout for labels and dropdowns
        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 0)  # label column stays compact
        grid_layout.setColumnStretch(1, 1)  # dropdown column expands

        # Input Device
        input_label = QLabel("Input Device:")
        self.input_dropdown = QComboBox()
        self._populate_device_inputs()
        grid_layout.addWidget(input_label, 0, 0)
        grid_layout.addWidget(self.input_dropdown, 0, 1)

        # Model
        model_label = QLabel("Model:")
        self.model_dropdown = QComboBox()
        self.model_dropdown.addItems(["tiny", "base"])
        grid_layout.addWidget(model_label, 1, 0)
        grid_layout.addWidget(self.model_dropdown, 1, 1)

        # Add grid layout to main vertical layout
        main_layout.addLayout(grid_layout)

        # Transcribe and clear button
        controls_layout = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.clicked.connect(self._toggle_transcribe)
        controls_layout.addWidget(self.transcribe_button, stretch=1)

        self.clearButton = QPushButton("Clear Output")
        self.clearButton.clicked.connect(self.clear_output)
        controls_layout.addWidget(self.clearButton)

        # Export button
        self.export_button = QPushButton("Export as TXT")
        self.export_button.clicked.connect(self.export_txt)
        controls_layout.addWidget(self.export_button)

        main_layout.addLayout(controls_layout)

        # Output table
        self.table = QTableWidget(0, 3)  # start with 0 rows, 3 columns
        self.table.setHorizontalHeaderLabels(["Start time", "End time", "Text Output"])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)  # make table read-only

        # Make third column stretch more
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        # Allow vertical scrolling (independent of button)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        main_layout.addWidget(self.table)

        # Output terminal
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFixedHeight(200)
        main_layout.addWidget(self.terminal)

    def _append_terminal(self, text):
        self.terminal.appendPlainText(text)
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())
        
    # Add device inputs with MME host API
    def _populate_device_inputs(self):
        devices = sd.query_devices()
        host_apis = sd.query_hostapis()

        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                api_name = host_apis[dev["hostapi"]]["name"]
                if "MME" in api_name:  # only show MME inputs
                    try:
                        sd.check_input_settings(device=idx, samplerate=16000, channels=1)
                        self.input_dropdown.addItem(f"{dev['name']} ({api_name})", idx)
                    except Exception:
                        continue
        self.input_dropdown.setCurrentIndex(2)  # select the Stereo Mix if available

    def _toggle_transcribe(self):
        if self.transcribe_button.text() == "Transcribe":
            self.transcribe_button.setText("Stop")
            self._start_transcription()
            self.lastTime = datetime.now()
        else:
            self.transcribe_button.setText("Transcribe")
            self._stop_transcription()

    def _on_new_segment(self, segment: Segment):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        timenow = datetime.now()

        start_time_str = self.lastTime.strftime("%H:%M:%S")
        end_time_str = timenow.strftime("%H:%M:%S")
        self.lastTime = timenow

        start_time = QTableWidgetItem(start_time_str)
        start_time.setTextAlignment(Qt.AlignCenter)
        end_time = QTableWidgetItem(end_time_str)
        end_time.setTextAlignment(Qt.AlignCenter)
        text_output = QTableWidgetItem(segment.text.strip())

        self.table.setItem(row_position, 0, start_time)
        self.table.setItem(row_position, 1, end_time)
        self.table.setItem(row_position, 2, text_output)
        self.table.resizeRowsToContents()
        self.table.scrollToBottom()
        self.segments.append(segment)
    
    def _start_transcription(self):
        if self.streamer is None:
            self._append_terminal("Loading model...")
            self.streamer = myStream.Streaming(
                model=self.model_dropdown.currentText(),
                input_device=self.input_dropdown.currentData(),
                segment_callback=self._on_new_segment
            )
            self.streamer.start()
            self._append_terminal("Transcription started.")
        else:
            self._append_terminal("Transcription already running.")

    def _stop_transcription(self):
        if self.streamer is not None:
            self.streamer.stop()
            self.streamer = None
            self._append_terminal("Transcription stopped.")
        else:
            self._append_terminal("Transcription not running.")
    
    def clear_output(self):
        self.table.setRowCount(0)
        self.segments = []
        self._append_terminal("Output cleared.")

    def export_txt(self):
        if not self.segments:
            self._append_terminal("No segments to export.")
            return

        date_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"transcription_{date_time}.txt"
        utils.output_txt(self.segments, output_filename)
        self._append_terminal(f"Transcription exported to {output_filename}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranscriberUI()
    window.show()
    sys.exit(app.exec_())
