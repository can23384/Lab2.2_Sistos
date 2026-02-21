import threading

# ============================================================
# Utilidades (sin random ni sleep para sincronización)
# ============================================================

class LCG:
    """Generador pseudo-aleatorio simple (sin usar random)."""
    def __init__(self, seed: int):
        self.state = seed & 0x7fffffff

    def next(self) -> int:
        self.state = (1103515245 * self.state + 12345) & 0x7fffffff
        return self.state


def spin(n: int) -> None:
    """Trabajo ocupado para simular tiempo."""
    x = 0
    for _ in range(n):
        x ^= (x << 1) & 0xFFFFFFFF


# ============================================================
# Bakery Lock (Exclusión mutua manual)
# ============================================================

class BakeryLock:
    def __init__(self, n: int):
        self.n = n
        self.choosing = [False] * n
        self.number = [0] * n

    def acquire(self, tid: int) -> None:
        self.choosing[tid] = True
        self.number[tid] = 1 + max(self.number)
        self.choosing[tid] = False

        for j in range(self.n):
            if j == tid:
                continue
            while self.choosing[j]:
                pass
            while self.number[j] != 0 and (
                self.number[j] < self.number[tid] or
                (self.number[j] == self.number[tid] and j < tid)
            ):
                pass

    def release(self, tid: int) -> None:
        self.number[tid] = 0


# ============================================================
# Semáforo Manual
# ============================================================

class Semaphore:
    def __init__(self, initial: int, nthreads: int):
        self.value = initial
        self.mutex = BakeryLock(nthreads)

    def wait(self, tid: int) -> None:
        while True:
            self.mutex.acquire(tid)
            if self.value > 0:
                self.value -= 1
                self.mutex.release(tid)
                return
            self.mutex.release(tid)
            spin(200)

    def signal(self, tid: int) -> None:
        self.mutex.acquire(tid)
        self.value += 1
        self.mutex.release(tid)


# ============================================================
# Monitor Portal Académico (Prioridad a Profesores)
# ============================================================

class PortalAcademico:
    def __init__(self, nthreads: int):
        # Semáforos del algoritmo clásico de prioridad escritores
        self.resource = Semaphore(1, nthreads)   # controla acceso al recurso compartido
        self.rmutex = Semaphore(1, nthreads)     # protege read_count
        self.wmutex = Semaphore(1, nthreads)     # protege write_count
        self.readTry = Semaphore(1, nthreads)    # bloquea lectores si hay escritores esperando
        self.total_lecturas = 0
        self.total_escrituras = 0
        self.max_lectores_simultaneos = 0
        self.max_escritores_simultaneos = 0

        self.read_count = 0
        self.write_count = 0

        # Estado del sistema
        self.notas = {"Sistemas Operativos": 0}

        # Solo para validación
        self.state_mutex = Semaphore(1, nthreads)
        self.print_mutex = Semaphore(1, nthreads)
        self.lectores_activos = 0
        self.escritores_activos = 0

    def log(self, tid: int, mensaje: str):
        self.print_mutex.wait(tid)
        print(mensaje)
        self.print_mutex.signal(tid)

    # =============================
    # LECTORES (Estudiantes)
    # =============================

    def estudiante_entra(self, tid: int):
        self.readTry.wait(tid)
        self.rmutex.wait(tid)

        self.read_count += 1
        if self.read_count == 1:
            self.resource.wait(tid)

        self.rmutex.signal(tid)
        self.readTry.signal(tid)

    def estudiante_sale(self, tid: int):
        self.rmutex.wait(tid)
        self.read_count -= 1
        if self.read_count == 0:
            self.resource.signal(tid)
        self.rmutex.signal(tid)

    # =============================
    # ESCRITORES (Profesores)
    # =============================

    def profesor_entra(self, tid: int):
        self.wmutex.wait(tid)
        self.write_count += 1
        if self.write_count == 1:
            self.readTry.wait(tid)
        self.wmutex.signal(tid)

        self.resource.wait(tid)

    def profesor_sale(self, tid: int):
        self.resource.signal(tid)

        self.wmutex.wait(tid)
        self.write_count -= 1
        if self.write_count == 0:
            self.readTry.signal(tid)
        self.wmutex.signal(tid)

    # =============================
    # Validación de exclusión
    # =============================

    def begin_read_cs(self, tid: int):
        error = False
        self.state_mutex.wait(tid)
        self.lectores_activos += 1
        self.total_lecturas += 1
        if self.escritores_activos != 0:
            error = True
        if self.lectores_activos > self.max_lectores_simultaneos:
            self.max_lectores_simultaneos = self.lectores_activos
        self.state_mutex.signal(tid)
        if error:
            self.log(tid, "ERROR: estudiante leyendo mientras profesor escribe")

    def end_read_cs(self, tid: int):
        self.state_mutex.wait(tid)
        self.lectores_activos -= 1
        self.state_mutex.signal(tid)

    def begin_write_cs(self, tid: int):
        error = False
        self.state_mutex.wait(tid)
        self.escritores_activos += 1
        self.total_escrituras += 1
        if self.escritores_activos != 1 or self.lectores_activos != 0:
            error = True
        if self.escritores_activos > self.max_escritores_simultaneos:
            self.max_escritores_simultaneos = self.escritores_activos
        self.state_mutex.signal(tid)
        if error:
            self.log(tid, "ERROR: violación exclusión mutua en escritura")

    def end_write_cs(self, tid: int):
        self.state_mutex.wait(tid)
        self.escritores_activos -= 1
        self.state_mutex.signal(tid)


# ============================================================
# Threads
# ============================================================

def estudiante_thread(tid, portal, stop_event):
    prng = LCG(1000 + tid)
    iteracion = 0

    while not stop_event.is_set():
        portal.estudiante_entra(tid)

        portal.begin_read_cs(tid)
        nota = portal.notas["Sistemas Operativos"]
        portal.log(tid, f"[ESTUDIANTE {tid}] >>> Consultando nota: {nota}")
        spin(1500 + prng.next() % 3000)
        portal.log(tid, f"[ESTUDIANTE {tid}] <<< Sale del portal")
        portal.end_read_cs(tid)

        portal.estudiante_sale(tid)
        spin(1000 + prng.next() % 4000)
        iteracion += 1


def profesor_thread(tid, portal, stop_event):
    prng = LCG(9000 + tid)
    iteracion = 0

    while not stop_event.is_set():
        portal.profesor_entra(tid)

        portal.begin_write_cs(tid)
        nota_anterior = portal.notas["Sistemas Operativos"]
        nueva_nota = nota_anterior + 1
        portal.log(tid, f"!!! [PROFESOR {tid}] >>> Publicando nueva nota: {nueva_nota}")
        spin(3000 + prng.next() % 5000)
        portal.notas["Sistemas Operativos"] = nueva_nota
        portal.log(tid, f"!!! [PROFESOR {tid}] <<< Actualización finalizada")
        portal.end_write_cs(tid)

        portal.profesor_sale(tid)
        spin(2000 + prng.next() % 5000)
        iteracion += 1


# ============================================================
# MAIN
# ============================================================

def main():
    res_est = input("Cantidad de estudiantes: (default 15)")
    NUM_ESTUDIANTES = int(res_est) if res_est.strip() else 15
    res_prof = input("Cantidad de profesores: (default 5)")
    NUM_PROFESORES = int(res_prof) if res_prof.strip() else 5
    res_dur = input("Duración en segundos (default 300s / 5min): ")
    DURACION = int(res_dur) if res_dur.strip() else 300
    

    nthreads = NUM_ESTUDIANTES + NUM_PROFESORES
    portal = PortalAcademico(nthreads)

    stop_event = threading.Event()
    threads = []

    for i in range(NUM_ESTUDIANTES):
        threads.append(threading.Thread(target=estudiante_thread, args=(i, portal, stop_event)))

    for i in range(NUM_PROFESORES):
        tid = NUM_ESTUDIANTES + i
        threads.append(threading.Thread(target=profesor_thread, args=(tid, portal, stop_event)))

    for t in threads:
        t.start()

    stop_event.wait(DURACION)
    stop_event.set()

    for t in threads:
        t.join()

    print("\n=== SIMULACIÓN FINALIZADA ===")
    print("Nota final publicada:", portal.notas["Sistemas Operativos"])

    print("\n=== MÉTRICAS ===")
    print("Total lecturas:", portal.total_lecturas)
    print("Total escrituras:", portal.total_escrituras)
    print("Máx lectores simultáneos:", portal.max_lectores_simultaneos)
    print("Máx escritores simultáneos:", portal.max_escritores_simultaneos)


if __name__ == "__main__":
    main()
