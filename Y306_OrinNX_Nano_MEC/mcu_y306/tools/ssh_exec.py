import sys
import paramiko


def main():
    host = "192.168.112.39"
    user = "nvidia"
    pwd = "nvidia"
    cmd = " ".join(sys.argv[1:])
    if not cmd:
        cmd = "echo connected"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=pwd, timeout=15)
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=False)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print("=== STDOUT ===")
    print(out)
    if err.strip():
        print("=== STDERR ===")
        print(err)
    print("=== exit %d ===" % stdout.channel.recv_exit_status())
    client.close()


if __name__ == "__main__":
    main()