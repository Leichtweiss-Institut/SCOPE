"""
Progress reporting for long-running processing steps, without QGIS.

Processing functions take an optional ``progress`` object and report each
stage they run through it. The GUI passes one that drives its progress bar;
scripts and tests get ``NullProgress``.
"""


class NullProgress:
    """Progress reporter that ignores everything."""

    def start(self, label, total=0):
        """Begin a stage. ``total`` is the amount of work, or 0 if unknown."""

    def update(self, done):
        """Report the amount of work done so far in the current stage."""

    def gdal_callback(self, complete, message=None, user_data=None):
        """GDAL progress callback for a stage started with ``total=1``."""
        self.update(complete)
        return 1
