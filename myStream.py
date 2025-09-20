import sounddevice as sd
import numpy as np
import pywhispercpp.constants as constants
from pywhispercpp.model import Model, Segment
import logging
import time
from PyQt5.QtCore import QObject, pyqtSignal
import sys

logging.basicConfig(level=logging.INFO)



class Streaming:
    '''
    Streaming class to handle audio streaming
    '''

    def __init__(self,
                 model='tiny',
                 input_device: int = 2,
                 redirect_output = False,
                 segment_callback=print):
        
        self.segment_callback = segment_callback
        self.input_device = input_device # Stereo Mix on Windows
        self.sample_rate = constants.WHISPER_SAMPLE_RATE
        self.channels = 1

        self.block_duration = 20  # block time in seconds
        self.block_size = int(self.sample_rate * self.block_duration)
        self.block = None

        self.stream = None
        self.redirect_output = redirect_output
        self.model = model
    

    def _transcribe_block(self):
        if self.block is None:
            return
        
        audio_data = np.array(self.block)
        # Appending zeros to the audio data as a workaround for small audio packets (small commands)
        audio_data = np.concatenate([audio_data, np.zeros((int(self.sample_rate) + 10))])
        # running the inference
        self.pywcpp.transcribe(audio_data,new_segment_callback=self.segment_callback)


    def _audio_callback(self, indata, frames, time, status):
        """
        This is called every block_duration seconds of stream input.
        """
        if status:
            logging.warning(F"underlying audio stack warning:{status}")

        assert frames == self.block_size
        audio_data = map(lambda x: (x + 1) / 2, indata)  # normalize from [-1,+1] to [0,1]
        audio_data = np.fromiter(audio_data, np.float16)
        self.block = audio_data

        self._transcribe_block()


    def start(self):
        if self.stream is not None:
            logging.warning("Stream already started ...")
            return
        self.pywcpp = Model(model=self.model, single_segment=True, redirect_whispercpp_logs_to=self.redirect_output)
        self.stream = sd.InputStream(samplerate=self.sample_rate,
                            device=self.input_device,
                            channels=self.channels,
                            blocksize=self.block_size,
                            callback=self._audio_callback)
        self.stream.start()
        logging.info("Started streaming ...")

    def stop(self):
        if self.stream is None:
            logging.warning("Stream not started ...")
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        logging.info("Streaming stopped.")

    @staticmethod
    def list_input_devices():
        """
        List all available input devices
        :return: None
        """
        print(sd.query_devices(kind='input'))



if __name__ == "__main__":
    streamer = Streaming(model='base', input_device=2)
    streamer.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        streamer.stop()