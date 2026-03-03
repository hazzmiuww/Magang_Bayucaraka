import cv2
import cv2.aruco as aruco
import numpy as np
import serial
import time
import threading

arduino_port = '/dev/ttyACM0'

WAIT_XY        = 3.5
WAIT_SHIFT     = 0.5
MAX_ROWS       = 14     
DELAY_LENGAN   = 2.0   
DELAY_CAPIT    = 2.5   

POJOK_CONFIG = {
    'KIRI_ATAS':   {'arah': 'KANAN', 'shift': 'MUNDUR'},
    'KANAN_ATAS':  {'arah': 'KIRI',  'shift': 'MUNDUR'},
    'KIRI_BAWAH':  {'arah': 'KANAN', 'shift': 'MAJU'},
    'KANAN_BAWAH': {'arah': 'KIRI',  'shift': 'MAJU'},
}

ARAH_BALIK  = {'KANAN': 'KIRI',   'KIRI': 'KANAN'} 
SHIFT_BALIK = {'MUNDUR': 'MAJU',  'MAJU': 'MUNDUR'}

def pilih_pojok():
    print("\n=== PILIH POJOK START ===")
    print("1. Kiri Atas\n2. Kanan Atas\n3. Kiri Bawah\n4. Kanan Bawah")
    while True:
        p = input("Masukkan angka (1-4): ").strip()
        if p == '1': return 'KIRI_ATAS'
        if p == '2': return 'KANAN_ATAS'
        if p == '3': return 'KIRI_BAWAH'
        if p == '4': return 'KANAN_BAWAH'
        print("Input kaga valid blok, coba lagi.")

class PatroliEngine:
    def __init__(self, pojok):
        cfg = POJOK_CONFIG[pojok]
        self.arah_init = cfg['arah']
        self.shift_init = cfg['shift']
        self.reset()

    def reset(self):
        self.row = 0
        self.direction = self.arah_init
        self.shift_cmd = self.shift_init
        self.phase = 'SIDE'
        self.done = False
        self.t_tunggu = 0
        self.next_fase = None
        self.riwayat = []
        self.ronde = 1
        self.antrian_r2 = []
        self.idx_r2 = 0

    def mulai_ronde2(self):
        self.ronde = 2
        self.antrian_r2 = []
        for (arah, shift) in reversed(self.riwayat):
            self.antrian_r2.append({
                'arah' : ARAH_BALIK[arah],
                'shift': SHIFT_BALIK[shift]
            })
        self.idx_r2 = 0
        self.phase  = 'SIDE'

    def tick(self):
        if self.done: return 'STOP'
        now = time.time()
        if self.phase == 'TUNGGU':
            if now < self.t_tunggu: return None
            self.phase = self.next_fase
            return None

        if self.ronde == 1:
            if self.phase == 'SIDE':
                self.riwayat.append((self.direction, self.shift_cmd))
                self.phase, self.t_tunggu, self.next_fase = 'TUNGGU', now + WAIT_XY, 'SHIFT'
                return self.direction
            if self.phase == 'SHIFT':
                self.row += 1
                if self.row >= MAX_ROWS:
                    self.done = True
                    return 'STOP'
                self.direction = ARAH_BALIK[self.direction]
                self.phase, self.t_tunggu, self.next_fase = 'TUNGGU', now + WAIT_SHIFT, 'SIDE'
                return self.shift_cmd

        if self.ronde == 2:
            if self.phase == 'SIDE':
                if self.idx_r2 >= len(self.antrian_r2):
                    self.done = True
                    return 'STOP'
                self.phase, self.t_tunggu, self.next_fase = 'TUNGGU', now + WAIT_XY, 'SHIFT'
                return self.antrian_r2[self.idx_r2]['arah']
            if self.phase == 'SHIFT':
                shift_cmd = self.antrian_r2[self.idx_r2]['shift']
                self.idx_r2 += 1
                if self.idx_r2 >= len(self.antrian_r2):
                    self.done = True
                    return 'STOP'
                self.phase, self.t_tunggu, self.next_fase = 'TUNGGU', now + WAIT_SHIFT, 'SIDE'
                return shift_cmd
        return None

class CapitEngine:
    def __init__(self):
        self.state = 'IDLE'
        self.mode = None   
        self.t_tunggu = 0

    def mulai(self, mode):
        self.mode, self.state = mode, 'TURUN'

    def selesai(self): return self.state == 'SELESAI'
    def idle(self): return self.state == 'IDLE'
    def reset(self): self.state = 'IDLE'

    def tick(self, kirim_fn):
        now = time.time()
        if self.state in ('IDLE', 'SELESAI'): return self.state
        if self.state in ('TUNGGU_TURUN', 'TUNGGU_AKSI', 'TUNGGU_NAIK'):
            if now < self.t_tunggu: return f'CAPIT: {self.state}'
            if self.state == 'TUNGGU_TURUN': self.state = 'AKSI'
            elif self.state == 'TUNGGU_AKSI': self.state = 'NAIK'
            elif self.state == 'TUNGGU_NAIK': self.state = 'SELESAI'
            return f'CAPIT: {self.state}'

        if self.state == 'TURUN':
            kirim_fn('LENGAN_TURUN')
            self.t_tunggu, self.state = now + DELAY_LENGAN, 'TUNGGU_TURUN'
            return 'CAPIT: TURUN'
        if self.state == 'AKSI':
            cmd = 'CAPIT_CLOSE' if self.mode == 'AMBIL' else 'CAPIT_OPEN'
            kirim_fn(cmd)
            self.t_tunggu, self.state = now + DELAY_CAPIT, 'TUNGGU_AKSI'
            return f'CAPIT: {cmd}'
        if self.state == 'NAIK':
            kirim_fn('LENGAN_NAIK')
            self.t_tunggu, self.state = now + DELAY_LENGAN, 'TUNGGU_NAIK'
            return 'CAPIT: NAIK'
        return self.state

class RobotAsek:
    def __init__(self, pojok):
        self.frame = None
        self.status = 'CARI_PAYLOAD'
        self.running = True
        self.last_command = ''
        self.patrol = PatroliEngine(pojok)
        self.capit = CapitEngine()
        self.payload_found = False
        try:
            self.arduino = serial.Serial(arduino_port, 9600, timeout=1)
            time.sleep(2)
            print('KONEK, AMAN KETUA')
        except:
            print('BLOM KECOLOK BLOK')
            self.arduino = None

    def tangkap_thread(self):
        cam = cv2.VideoCapture(2)
        while self.running:
            ret, img = cam.read()
            if ret: self.frame = cv2.resize(img, (640, 480))

    def kirim(self, msg):
        if self.arduino and msg != self.last_command:
            self.arduino.write(f"<{msg}>\n".encode())
            print(f'KIRIM: {msg}')
            self.last_command = msg

    def kirim_paksa(self, msg):
        if self.arduino:
            self.arduino.write(f"<{msg}>\n".encode())
            print(f'KIRIM: {msg}')
            self.last_command = msg

    def mulai(self):
        threading.Thread(target=self.tangkap_thread, daemon=True).start()
        ar_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
        detector = aruco.ArucoDetector(ar_dict, aruco.DetectorParameters())

        while self.running:
            if self.frame is None: continue
            frame_cpy = self.frame.copy()
            gray = cv2.cvtColor(frame_cpy, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)

            cv2.line(frame_cpy, (320, 220), (320, 260), (0, 255, 0), 2)
            cv2.line(frame_cpy, (300, 240), (340, 240), (0, 255, 0), 2)
            cv2.putText(frame_cpy, f'STATUS: {self.status}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            if self.status == 'SELESAI':
                self.kirim('STOP')
                cv2.putText(frame_cpy, 'MISI KELAR COK! CABUT!', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                cv2.imshow('PEMANTAU', frame_cpy)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break
                continue 

            if not self.capit.idle():
                label = self.capit.tick(self.kirim_paksa)
                cv2.putText(frame_cpy, label, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 128, 0), 2)
                if self.capit.selesai():
                    mode_selesai = self.capit.mode
                    self.capit.reset()
                    self.last_command = ''
                    if mode_selesai == 'AMBIL':
                        self.status = 'CARI_TARGET'
                        self.payload_found = True
                    elif mode_selesai == 'TARUH':
                        self.status = 'SELESAI' # LANGSUNG TAMAT!
                cv2.imshow('PEMANTAU', frame_cpy)
                cv2.waitKey(1)
                continue   

            target_id = 0 if self.status == 'CARI_PAYLOAD' else 1

            if ids is not None and target_id in ids.flatten():

                self.patrol.t_tunggu = time.time() + WAIT_XY 

                aruco.drawDetectedMarkers(frame_cpy, corners, ids)
                flat_ids = ids.flatten()
                index = np.where(flat_ids == target_id)[0][0]
                c = corners[index][0]

                cx = int((c[0][0] + c[1][0] + c[2][0] + c[3][0]) / 4)
                cy = int((c[0][1] + c[1][1] + c[2][1] + c[3][1]) / 4)
                cv2.putText(frame_cpy, f'X: {cx} Y: {cy}', (cx, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                if cx < 280:
                    self.kirim('KIRI')
                    cv2.putText(frame_cpy, 'KIRI DIKIT', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                elif cx > 360:
                    self.kirim('KANAN')
                    cv2.putText(frame_cpy, 'KANAN DIKIT', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                elif cy < 250:
                    self.kirim('MAJU')
                    cv2.putText(frame_cpy, 'MAJU TERUS', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    self.kirim('STOP')
                    cv2.putText(frame_cpy, 'PAS! EKSEKUSI!', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    if self.status == 'CARI_PAYLOAD':
                        self.capit.mulai('AMBIL')
                        self.status = 'CARI_TARGET'
                    else:
                        self.capit.mulai('TARUH')
            else:
                if self.status == 'CARI_TARGET' and self.payload_found:
                    if self.patrol.ronde == 1 and self.patrol.phase == 'SHIFT':
                        self.patrol.mulai_ronde2()
                        self.payload_found = False

                if self.status != 'SELESAI':
                    cmd = self.patrol.tick()
                    if cmd is not None: self.kirim(cmd)
                    label = f'PATROLI R{self.patrol.ronde}... ({self.patrol.direction})'
                    cv2.putText(frame_cpy, label, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    self.kirim('STOP')
                    cv2.putText(frame_cpy, 'MISI KELAR COK!', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

                    if self.status == 'CARI_PAYLOAD':
                        self.capit.mulai('AMBIL')
                    elif self.status == 'CARI_TARGET':
                        self.capit.mulai('TARUH')

            cv2.imshow('PEMANTAU', frame_cpy)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
                break

        if self.arduino:
            self.arduino.write(b"<STOP>\n")
            self.arduino.close()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    bot = RobotAsek(pilih_pojok())
    bot.mulai()