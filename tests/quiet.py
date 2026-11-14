"""quiet(): silence what commands print while a test runs them in-process, both their own lines (sys.stdout) and the
programs they start (file descriptor 1, and 2 with stderr=True), so a green run shows only dots. A test that checks a
line still captures it itself (redirect_stdout or capture_output inside), and unittest reports on stderr, never fd 1."""
import contextlib, io, os, sys


@contextlib.contextmanager
def quiet(stderr=False):
    fds = (1, 2) if stderr else (1,)
    sys.stdout.flush()
    sys.stderr.flush()
    saved, null = [os.dup(fd) for fd in fds], os.open(os.devnull, os.O_WRONLY)
    try:
        for fd in fds:
            os.dup2(null, fd)
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        sys.stdout.flush()
        for fd, copy in zip(fds, saved):
            os.dup2(copy, fd)
            os.close(copy)
        os.close(null)


HELD = []


def setUpModule():
    """A test module whose in-process commands print imports these two, so its whole run is quiet on stdout."""
    HELD.append(quiet())
    HELD[-1].__enter__()


def tearDownModule():
    HELD.pop().__exit__(None, None, None)
