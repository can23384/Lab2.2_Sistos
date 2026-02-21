import threading
import time
import random

# --- EXCLUSIÓN MUTUA DESDE CERO ---
class BakeryLock:
    def __init__(self, n_hilos):
        self.n = n_hilos
        # Variables de estado (listas simples, sin objetos de threading)
        self.eligiendo = [False] * n_hilos
        self.numero = [0] * n_hilos

    def lock(self, i):
        # 1. El hilo 'i' toma un número de turno
        self.eligiendo[i] = True
        max_actual = 0
        for val in self.numero:
            if val > max_actual:
                max_actual = val
        self.numero[i] = max_actual + 1
        self.eligiendo[i] = False

        # 2. El hilo 'i' espera su turno comparándose con todos los demás
        for j in range(self.n):
            # Esperar si el hilo j está eligiendo número
            while self.eligiendo[j]:
                pass
            
            # Esperar si el hilo j tiene un número menor (prioridad)
            # O si tiene el mismo número pero un ID menor
            while (self.numero[j] != 0 and 
                   (self.numero[j] < self.numero[i] or 
                    (self.numero[j] == self.numero[i] and j < i))):
                pass

    def unlock(self, i):
        self.numero[i] = 0

# --- CONTROLADOR DEL PORTAL CON PRIORIDAD A ESCRITORES ---
class PortalNotas:
    def __init__(self, total_participantes):
        self.notas = {"Tarea 1": 100, "Parcial": 85, "Laboratorio": 90}
        self.lock_interno = BakeryLock(total_participantes)
        
        # Variables de control para la lógica Readers-Writers
        self.lectores_leyendo = 0
        self.auxiliares_esperando = 0
        self.escribiendo_actualmente = False

    def consultar_notas(self, id_hilo):
        # Fase de Entrada (Protocolo de Lector)
        while True:
            self.lock_interno.lock(id_hilo)
            # Condición Prioridad Escritores: Pasa si no hay auxiliares esperando ni escribiendo
            if self.auxiliares_esperando == 0 and not self.escribiendo_actualmente:
                self.lectores_leyendo += 1
                self.lock_interno.unlock(id_hilo)
                break
            self.lock_interno.unlock(id_hilo)
            time.sleep(0.05) # Pequeña pausa para no saturar el CPU

        # --- SECCIÓN CRÍTICA ---
        print(f"  [ESTUDIANTE {id_hilo}] Leyendo notas: {self.notas}")
        time.sleep(random.uniform(0.5, 1.2)) # Simula tiempo de lectura

        # Fase de Salida
        self.lock_interno.lock(id_hilo)
        self.lectores_leyendo -= 1
        self.lock_interno.unlock(id_hilo)
        print(f"  [ESTUDIANTE {id_hilo}] Salió del portal.")

    def actualizar_notas(self, id_hilo):
        # Fase de Entrada (Protocolo de Escritor)
        self.lock_interno.lock(id_hilo)
        self.auxiliares_esperando += 1
        self.lock_interno.unlock(id_hilo)

        while True:
            self.lock_interno.lock(id_hilo)
            # Solo entra si no hay nadie leyendo ni otro auxiliar escribiendo
            if self.lectores_leyendo == 0 and not self.escribiendo_actualmente:
                self.escribiendo_actualmente = True
                self.lock_interno.unlock(id_hilo)
                break
            self.lock_interno.unlock(id_hilo)
            time.sleep(0.05)

        # --- SECCIÓN CRÍTICA ---
        trabajo = random.choice(list(self.notas.keys()))
        nueva_nota = random.randint(60, 100)
        self.notas[trabajo] = nueva_nota
        print(f"!!! [AUXILIAR {id_hilo}] ACTUALIZANDO {trabajo} a {nueva_nota} pts.")
        time.sleep(2.0) # La actualización es un proceso pesado

        # Fase de Salida
        self.lock_interno.lock(id_hilo)
        self.escribiendo_actualmente = False
        self.auxiliares_esperando -= 1
        self.lock_interno.unlock(id_hilo)
        print(f"!!! [AUXILIAR {id_hilo}] Finalizó actualización y liberó el portal.")

# --- SIMULACIÓN ---
def tarea_estudiante(id_hilo, portal, tiempo_limite):
    while time.time() < tiempo_limite:
        portal.consultar_notas(id_hilo)
        time.sleep(random.uniform(2, 4)) # Tiempo entre consultas

def tarea_auxiliar(id_hilo, portal, tiempo_limite):
    while time.time() < tiempo_limite:
        portal.actualizar_notas(id_hilo)
        time.sleep(random.uniform(8, 12)) # Los auxiliares no actualizan tan seguido

if __name__ == "__main__":
    # Configuración de hilos
    CANT_ESTUDIANTES = 5
    CANT_AUXILIARES = 2
    TOTAL_HILOS = CANT_ESTUDIANTES + CANT_AUXILIARES
    DURACION = 60 # Segundos mínimos requeridos
    
    portal = PortalNotas(TOTAL_HILOS)
    hilos = []
    tiempo_final = time.time() + DURACION

    print(f"Iniciando portal con {CANT_ESTUDIANTES} estudiantes y {CANT_AUXILIARES} auxiliares...")

    # Crear instancias de estudiantes (ID del 0 al 4)
    for i in range(CANT_ESTUDIANTES):
        t = threading.Thread(target=tarea_estudiante, args=(i, portal, tiempo_final))
        hilos.append(t)

    # Crear instancias de auxiliares (ID del 5 al 6)
    for i in range(CANT_AUXILIARES):
        t = threading.Thread(target=tarea_auxiliar, args=(CANT_ESTUDIANTES + i, portal, tiempo_final))
        hilos.append(t)

    # Iniciar todos
    for t in hilos:
        t.start()

    # Esperar a que terminen
    for t in hilos:
        t.join()

    print("\n--- Simulación de 60 segundos completada ---")