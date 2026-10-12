#!/usr/bin/env python3
"""Controllo TCP/IP e acquisizione CSV a 1 Sa/s per ET System LAB/HP."""

import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import socket
import sys
import time


def positive_decimal(value):
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("serve un numero in notazione decimale") from exc
    if not number.is_finite() or number <= 0:
        raise argparse.ArgumentTypeError("serve un numero finito maggiore di zero")
    return number


class LabHP:
    def __init__(self, connection, timeout=2.0):
        self.connection = connection
        self.timeout = timeout
        self.sent = set()

    def send(self, command):
        self.sent.add(command.upper())
        self.connection.sendall((command + "\r").encode("ascii"))

    def query(self, command):
        self.send(command)
        deadline = time.monotonic() + self.timeout
        line = bytearray()
        while time.monotonic() < deadline:
            try:
                byte = self.connection.recv(1)
            except socket.timeout:
                continue
            if not byte:
                raise ConnectionError("connessione TCP chiusa dall'alimentatore")
            if byte in (b"\r", b"\n"):
                if not line:
                    continue
                result = line.decode("ascii", errors="replace").strip()
                line.clear()
                # Il dispositivo può fare eco carattere per carattere, anche
                # dei comandi di impostazione inviati poco prima della query.
                if result.upper() in self.sent:
                    self.sent.discard(result.upper())
                    continue
                if result.upper().startswith(command.upper() + ","):
                    return result
                raise RuntimeError(f"risposta inattesa a {command}: {result!r}")
            else:
                line.extend(byte)
                if len(line) > 256:
                    raise RuntimeError("risposta TCP troppo lunga")
        raise TimeoutError(f"nessuna risposta a {command!r} entro {self.timeout:g} s")

    def value(self, command, unit):
        response = self.query(command)
        pattern = rf"{re.escape(command)},([+-]?(?:\d+(?:\.\d*)?|\.\d+)){re.escape(unit)}"
        match = re.fullmatch(pattern, response, re.IGNORECASE)
        if not match:
            raise RuntimeError(f"formato inatteso per {command}: {response!r}")
        return Decimal(match.group(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="indirizzo IP o nome host dell'alimentatore")
    parser.add_argument("--port", type=int, default=10001, help="porta TCP (default: 10001)")
    parser.add_argument("--voltage", required=True, type=positive_decimal, help="tensione richiesta in V")
    parser.add_argument("--current", required=True, type=positive_decimal, help="limite di corrente in A")
    parser.add_argument("--output", help="file CSV; default: labhp_YYYYmmdd_HHMMSS.csv")
    parser.add_argument("--timeout", type=positive_decimal, default=Decimal("2"), help="timeout per query in s")
    parser.add_argument("--ovp", type=positive_decimal, help="imposta la protezione da sovratensione in V")
    args = parser.parse_args()
    if args.ovp is not None and args.ovp <= args.voltage:
        parser.error("--ovp deve essere maggiore di --voltage")

    if not 1 <= args.port <= 65535:
        parser.error("--port deve essere tra 1 e 65535")

    filename = args.output or datetime.now().strftime("labhp_%Y%m%d_%H%M%S.csv")
    try:
        with open(filename, "x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("timestamp_utc", "elapsed_s", "voltage_V", "current_A"))
            file.flush()
            connection = socket.create_connection((args.host, args.port), timeout=float(args.timeout))
            with closing(connection):
                connection.settimeout(0.1)
                device = LabHP(connection, float(args.timeout))
                output_enabled = False
                try:
                    max_voltage = device.value("LIMU", "V")
                    max_current = device.value("LIMI", "A")
                    if args.voltage > max_voltage or args.current > max_current:
                        raise ValueError(f"richiesta oltre i limiti: {max_voltage} V, {max_current} A")

                    device.send("GTR")
                    device.send("SB,S")
                    device.send("MODE,UI")
                    if args.ovp is not None:
                        device.send(f"OVP,{args.ovp}")
                    ovp = device.value("OVP", "V")
                    if ovp <= args.voltage:
                        raise ValueError(f"OVP attuale ({ovp} V) non superiore alla tensione richiesta")
                    device.send(f"UA,{args.voltage}")
                    device.send(f"IA,{args.current}")
                    actual_voltage = device.value("UA", "V")
                    actual_current = device.value("IA", "A")
                    if abs(actual_voltage - args.voltage) > max(max_voltage * Decimal("0.001"), Decimal("0.001")):
                        raise RuntimeError(f"setpoint tensione inatteso: {actual_voltage} V")
                    if abs(actual_current - args.current) > max(max_current * Decimal("0.001"), Decimal("0.001")):
                        raise RuntimeError(f"setpoint corrente inatteso: {actual_current} A")

                    output_enabled = True
                    device.send("SB,R")
                    print(f"Uscita attiva: {actual_voltage} V, limite {actual_current} A; CSV: {filename}", flush=True)
                    start = time.monotonic()
                    sample_number = 0
                    while True:
                        target = start + sample_number
                        delay = target - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                        voltage = device.value("MU", "V")
                        current = device.value("MI", "A")
                        elapsed = time.monotonic() - start
                        writer.writerow((datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                         f"{elapsed:.3f}", str(voltage), str(current)))
                        file.flush()
                        sample_number = max(sample_number + 1, int(elapsed) + 1)
                finally:
                    # Anche in caso di Ctrl+C o errore di acquisizione, prova a
                    # mettere l'alimentatore in standby prima di chiudere la porta.
                    if output_enabled:
                        try:
                            device.send("SB,S")
                        except Exception as exc:
                            print(f"ATTENZIONE: invio del comando standby fallito: {exc}", file=sys.stderr)
                        else:
                            print("Comando standby inviato.", file=sys.stderr)
    except KeyboardInterrupt:
        print("Acquisizione interrotta dall'utente.", file=sys.stderr)
    except Exception as exc:
        parser.exit(1, f"Errore: {exc}\n")


if __name__ == "__main__":
    main()
