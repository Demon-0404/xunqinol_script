"""Interactive portal redirect test on 天音"""
import frida, time, sys, cmd, json

class PortalTester(cmd.Cmd):
    prompt = '(portal) '

    def __init__(self, script):
        super().__init__()
        self.script = script

    def _call(self, fn_name, *args):
        try:
            fn = getattr(self.script.exports_sync, fn_name)
            return fn(*args)
        except Exception as e:
            return f'Error: {e}'

    def do_key(self, arg):
        """Show current XOR session key"""
        k = self._call('get_key')
        print(f'XOR Key: 0x{k:02x}' if k else 'Key: not detected yet')

    def do_capture_start(self, arg):
        """Start raw recv capture"""
        print(self._call('start_capture'))

    def do_capture_stop(self, arg):
        """Stop capture and show plain text"""
        plain = self._call('stop_capture')
        print(f'Captured plain ({len(plain)//2}B): {plain}')

    def do_inject(self, plain_hex):
        """Inject plain hex data on next portal use.
Usage: inject <plain_hex>
The injection will be armed and trigger on the next portal send + large recv."""
        if not plain_hex:
            print('Usage: inject <plain_hex>')
            return
        print(self._call('inject', plain_hex))

    def do_redirect(self, plain_hex):
        """Arm portal redirect: replace outgoing portal packets with this plain hex.
Usage: redirect <plain_hex_of_target_portal_packet>"""
        if not plain_hex:
            print('Usage: redirect <plain_hex>')
            return
        print(self._call('arm_portal_redirect', plain_hex))

    def do_redirect_off(self, arg):
        """Disable portal redirect"""
        print(self._call('disable_portal_redirect'))

    def do_byte_xor(self, args):
        """Arm byte redirect at position 24-27 with XOR key.
Usage: byte_xor <4_byte_xor_hex>
Example: byte_xor a0b0c0d0"""
        if not args:
            print('Usage: byte_xor <xorkey_hex>')
            return
        print(self._call('arm_byte_redirect', args))

    def do_byte_xor_at(self, args):
        """Arm byte redirect at custom position.
Usage: byte_xor_at <start_pos> <xorkey_hex>"""
        parts = args.split()
        if len(parts) != 2:
            print('Usage: byte_xor_at <start_pos> <xorkey_hex>')
            return
        print(self._call('arm_byte_redirect_at', int(parts[0]), parts[1]))

    def do_byte_off(self, arg):
        """Disable byte redirect"""
        print(self._call('disable_byte_redirect'))

    def do_stats(self, arg):
        """Show current status"""
        s = self._call('get_stats')
        print(json.dumps(json.loads(s), indent=2))

    def do_reset(self, arg):
        """Disable all hooks"""
        print(self._call('disable_all'))

    def do_exit(self, arg):
        """Exit"""
        return True

    def do_quit(self, arg):
        """Exit"""
        return True

    def emptyline(self):
        pass

def on_msg(msg, data):
    payload = msg.get('payload', {})
    if not isinstance(payload, dict): return
    t = payload.get('t', '?')
    m = payload.get('msg', '')

    if t == 'ready':
        print(f'[*] {m}')
    elif t == 'key':
        print(f'[KEY] XOR key = 0x{payload["key"]:02x}')
    elif t == 'portal_send':
        print(f'[PORTAL] Captured plain: {payload["plain"]}')
    elif t == 'inj_armed':
        print(f'[INJECT] {m}')
    elif t == 'inj_wait':
        pass  # too verbose
    elif t == 'inj_chunk':
        print(f'[INJECT] Chunk: wrote {payload["wrote"]}B ({payload["offset"]}/{payload["total"]})')
    elif t == 'inj_done':
        print(f'[INJECT] {m}')
    elif t == 'recv_type3':
        print(f'[RECV] Type 3 data: {payload["len"]}B')
    elif t == 'portal_redirect':
        print(f'[REDIRECT] {m}')
    elif t == 'byte_redirect':
        print(f'[BYTE_XOR] {m}')
    elif t == 'recv_blocked':
        print(f'[BLOCK] {m}')
    elif t == 'recv_filter_hb':
        pass
    elif t == 'close_blocked':
        print(f'[BLOCK] close() blocked (total: {payload["total"]})')
    elif t == 'shutdown_blocked':
        print(f'[BLOCK] shutdown() blocked (total: {payload["total"]})')
    elif t == 'silence_off':
        print(f'[SILENCE] {m}')
    elif t == 'fake_recv':
        pass
    sys.stdout.flush()

def main():
    with open('portal_redirect_test.js', 'r') as f:
        JS = f.read()

    print("Connecting to 天音 (127.0.0.1:27056)...")
    dev = frida.get_device_manager().add_remote_device('127.0.0.1:27056')
    session = dev.attach(2793)
    print(f"Attached to PID 2793")

    script = session.create_script(JS)
    script.on('message', on_msg)
    script.load()
    time.sleep(1)

    tester = PortalTester(script)
    try:
        tester.cmdloop()
    except KeyboardInterrupt:
        print('\nInterrupted')
    finally:
        session.detach()
        print('Disconnected')

if __name__ == '__main__':
    main()
