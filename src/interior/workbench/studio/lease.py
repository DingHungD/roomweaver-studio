"""OS-backed single service lease; process exit releases it without deleting user data."""
import os
from pathlib import Path

class Lease:
    def __init__(self,directory):
        path=Path(directory)/'service.lock'
        path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=path.open('a+b')
        if path.stat().st_size==0:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError('本機工作台已在使用此資料目錄，請先關閉既有服務') from None

    def close(self):
        if self.stream.closed:return
        self.stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.stream,fcntl.LOCK_UN)
        self.stream.close()
