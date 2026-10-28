"""
Tests für tools.py – laufen ohne Ollama und ohne Qdrant.

Statt echter Dateien in data/ nutzen die Tests einen leeren Ordner (tmp_path),
und alles, was nach außen geht (Qdrant-Suche, App öffnen), wird ersetzt (Mock).
"""
import subprocess

import pytest

import tools


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
  # tools.py liest aus DATA_DIR, für jeden Test ein frischer, leerer Ordner
  monkeypatch.setattr(tools, 'DATA_DIR', str(tmp_path))
  return tmp_path


# ---------- read_file ----------
def test_read_file_liest_datei(data_dir):
  (data_dir / 'notiz.txt').write_text('Hallo s(i)oul', encoding='utf-8')
  assert tools.read_file('notiz.txt') == 'Hallo s(i)oul'

def test_read_file_blockiert_pfad_nach_draussen(data_dir):
  # Datei liegt eine Ebene ÜBER data/ und darf nicht lesbar sein
  (data_dir.parent / 'geheim.txt').write_text('Passwort', encoding='utf-8')
  result = tools.read_file('../geheim.txt')
  assert 'Passwort' not in result
  assert 'nicht gefunden' in result

def test_read_file_kuerzt_grosse_dateien(data_dir):
  (data_dir / 'gross.txt').write_text('a' * (tools.MAX_FILE_CHARS + 100), encoding='utf-8')
  result = tools.read_file('gross.txt')
  assert result.startswith('a' * tools.MAX_FILE_CHARS)
  assert 'gekürzt' in result


# ---------- list_files ----------
def test_list_files_leerer_ordner(data_dir):
  assert tools.list_files() == 'Der Ordner data/ ist leer.'

def test_list_files_sortiert_und_ohne_versteckte(data_dir):
  for name in ['b.txt', 'a.txt', '.DS_Store']:
    (data_dir / name).write_text('x', encoding='utf-8')
  assert tools.list_files() == 'a.txt\nb.txt'


# ---------- open_app ----------
def test_open_app_verweigert_unbekannte_app():
  assert 'darf ich nicht öffnen' in tools.open_app('Terminal')

def test_open_app_ignoriert_gross_kleinschreibung(monkeypatch):
  # subprocess.run ersetzen: der Test soll prüfen, nicht wirklich den Rechner öffnen
  aufrufe = []
  def fake_run(cmd, **kwargs):
    aufrufe.append(cmd)
    return subprocess.CompletedProcess(cmd, returncode=0)
  monkeypatch.setattr(tools.subprocess, 'run', fake_run)
  monkeypatch.setattr(tools.sys, 'platform', 'darwin')

  assert tools.open_app('  rechner ') == 'Rechner wurde geöffnet.'
  assert aufrufe == [['open', '-a', 'Calculator']]


# ---------- search_documents (Qdrant wird ersetzt) ----------
def test_search_documents_ohne_treffer(monkeypatch):
  monkeypatch.setattr(tools, 'retrieve', lambda query, top_n: [])
  assert tools.search_documents('Wetter') == 'Keine passenden Abschnitte gefunden.'

def test_search_documents_formatiert_treffer(monkeypatch):
  monkeypatch.setattr(tools, 'retrieve', lambda query, top_n: [('s(i)oul läuft lokal', 0.874, 'sioul.txt')])
  assert tools.search_documents('Was ist s(i)oul?') == '[sioul.txt, Ähnlichkeit 0.87] s(i)oul läuft lokal'


# ---------- run_tool ----------
def test_run_tool_unbekanntes_tool():
  assert 'gibt es nicht' in tools.run_tool('rm_rf', {})

def test_run_tool_falsche_argumente():
  assert 'falsche Argumente' in tools.run_tool('current_datetime', {'foo': 1})

def test_run_tool_faengt_fehler_ab(monkeypatch):
  def kaputt():
    raise RuntimeError('Qdrant nicht erreichbar')
  monkeypatch.setitem(tools.TOOLS, 'list_files', (kaputt, tools.TOOLS['list_files'][1]))
  assert tools.run_tool('list_files', None) == 'Fehler in list_files: Qdrant nicht erreichbar'


# ---------- Schemas ----------
def test_schema_namen_passen_zu_tools():
  # Sonst ruft das Modell ein Tool mit einem Namen auf, den run_tool nicht kennt
  for name, (_, schema) in tools.TOOLS.items():
    assert schema['function']['name'] == name

def test_open_app_schema_nur_erlaubte_apps():
  enum = tools.TOOLS['open_app'][1]['function']['parameters']['properties']['app']['enum']
  assert enum == list(tools.APPS)
