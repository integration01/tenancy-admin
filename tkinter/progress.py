import logging
from threading import Lock

class Progress():

    def __init__(self, progress_val: int):
        self.lock = Lock()
        self.loaded = 0
        self.to_load = 0

        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
        self.logger = logging.getLogger('oci-policy-analysis-progress')
        self.logger.info("Main Progress Meter")

        self.progressbar_val = progress_val

    def set_to_load(self, to_load: int):
        self.logger.info(f"Set to load: {to_load}")
        self.loaded = 0
        self.to_load = to_load

    def progress_indicator(self, future):
        # global lock, loaded, to_load

        # obtain the lock
        with self.lock:
            # Increase loaded
            self.loaded += 1

            # Figure completion
            comp_step = int(self.loaded / self.to_load * 100)
            self.logger.debug(f"Completed {self.loaded} of {self.to_load} for a step of {comp_step}")
            if (comp_step%20 == 0 and self.loaded%10 == 0):
                self.logger.info(f"Completed {self.loaded} of {self.to_load} for a step of {comp_step}")

            # Report progress via progress bar (int version)
            self.progressbar_val = comp_step
