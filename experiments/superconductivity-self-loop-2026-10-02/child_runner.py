"""Hold an OS lock until the owned child exits, including after parent failure."""
import subprocess
import sys
from runtime import exclusive

if __name__=='__main__':
    with exclusive(sys.argv[1]):
        command=sys.argv[3:]
        process=subprocess.Popen(command,stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr)
        raise SystemExit(process.wait())
