#!/usr/bin/env python3
"""Atualiza a tábua de marés embutida em index.html a partir do PDF oficial DHN.

A página não consegue baixar o PDF sozinha (o site da AESA não permite acesso pelo
navegador), então as baixa-mares ficam gravadas dentro do HTML. Rode este script
uma vez por ano, quando a Marinha publicar a tábua nova do Porto de Cabedelo.

Requer Python >= 3.10 e: pip install "pdfplumber>=0.11,<1"

Uso:
    python atualizar_mares.py TABUA_CABEDELO_2027.pdf
    python atualizar_mares.py https://.../PORTO-DE-CABEDELO.pdf
    python atualizar_mares.py tabua.pdf --html outro/index.html

O ano é lido do cabeçalho do PDF. Dados de outros anos já gravados são mantidos;
os do mesmo ano são substituídos. Alturas em metros sobre o nível de redução DHN,
horários em America/Recife (UTC−3).
"""
import argparse
import calendar
import io
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pdfplumber

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
         'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
CABECALHO = re.compile(r'PORTO DE CABEDELO.*?-\s*(\d{4})')
BLOCO = re.compile(r'(<script type="application/json" id="mares">)(.*?)(</script>)', re.S)


def load(source):
    if source.startswith(('https://', 'http://')):
        request = urllib.request.Request(source, headers={'User-Agent': 'PlanejadorMergulho/1.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    return Path(source).read_bytes()


def tides(data):
    """Lê o layout DHN: quatro meses por página, duas colunas de dias por mês.

    Falha explicitamente se o layout mudar; não adivinha alturas.
    Retorna (ano, lista de baixa-mares [(datetime, altura)]).
    """
    events, found, years = [], set(), set()
    if not data.startswith(b'%PDF'):
        raise ValueError('O arquivo não é um PDF.')
    with pdfplumber.open(io.BytesIO(data)) as doc:
        for page in doc.pages:
            text = page.extract_text() or ''
            header = CABECALHO.search(text)
            if not header:
                continue
            if 'UTC -03' not in text:
                raise ValueError('Fuso da tábua diferente de UTC−3.')
            year = int(header[1])
            years.add(year)
            words = page.extract_words()
            headings = sorted([w for w in words if w['text'] in MESES], key=lambda w: w['x0'])
            if len(headings) != 4:
                raise ValueError('Layout DHN não reconhecido: esperados quatro meses por página.')
            top = max(w['bottom'] for w in headings)
            anchors = sorted([w for w in words if w['text'] in ('01', '17')
                              and top < w['top'] < top + 28], key=lambda w: w['x0'])
            if len(anchors) != 8:
                raise ValueError('Layout DHN não reconhecido: colunas de dias ausentes.')
            for slot, heading in enumerate(headings):
                month = MESES.index(heading['text']) + 1
                found.add(month)
                for col in range(2):
                    index = slot * 2 + col
                    left = anchors[index]['x0'] - 1
                    right = anchors[index + 1]['x0'] - 1 if index < 7 else page.width - 25
                    block = page.crop((left, top + 1, right, page.height - 25)).extract_text() or ''
                    day = None
                    for line in block.splitlines():
                        first = re.match(r'^(\d{2})\s+(\d{4})\s+(-?\d+\.\d+)\s*$', line)
                        if first:
                            day = int(first[1])
                        pair = re.search(r'(\d{4})\s+(-?\d+\.\d+)\s*$', line)
                        if pair and day:
                            clock = pair[1]
                            events.append((datetime(year, month, day, int(clock[:2]), int(clock[2:])),
                                           float(pair[2])))
    if not years:
        raise ValueError('O PDF não parece ser a tábua DHN do Porto de Cabedelo.')
    if len(years) > 1:
        raise ValueError(f'PDF com mais de um ano: {sorted(years)}.')
    year = years.pop()
    if found != set(range(1, 13)):
        raise ValueError(f'Tábua incompleta: meses encontrados {sorted(found)}.')
    for month in found:
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            count = sum(t.month == month and t.day == day for t, _ in events)
            if count not in (3, 4):
                raise ValueError(f'Extração incompleta: {year}-{month:02}-{day:02}: {count} eventos.')
    events.sort()
    # Preamar e baixa-mar se alternam: baixa-mar é o evento abaixo dos vizinhos
    # (no primeiro e no último evento do ano, abaixo do único vizinho).
    lows = []
    for i, (t, h) in enumerate(events):
        neighbors = [events[j][1] for j in (i - 1, i + 1) if 0 <= j < len(events)]
        if all(h < n for n in neighbors):
            lows.append((t, h))
    return year, lows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('pdf', nargs='+', help='caminho ou URL do PDF DHN do Porto de Cabedelo (um por ano)')
    p.add_argument('--html', default=str(Path(__file__).with_name('index.html')),
                   help='página a atualizar (padrão: index.html ao lado deste script)')
    args = p.parse_args()

    page = Path(args.html)
    content = page.read_text(encoding='utf-8')
    match = BLOCO.search(content)
    if not match:
        raise ValueError(f'Bloco de marés não encontrado em {page}.')
    table = json.loads(match[2])

    for source in args.pdf:
        year, lows = tides(load(source))
        kept = [x for x in table['baixamares'] if not x[0].startswith(f'{year}-')]
        table['baixamares'] = sorted(kept + [[t.strftime('%Y-%m-%dT%H:%M'), h] for t, h in lows])
        origin = source if source.startswith(('https://', 'http://')) else Path(source).name
        table['origem'] = {**table.get('origem', {}), str(year): origin}
        print(f'{year}: {len(lows)} baixa-mares lidas de {source}')

    table['anos'] = sorted({int(x[0][:4]) for x in table['baixamares']})
    text = json.dumps(table, ensure_ascii=False)
    if '</' in text:
        raise ValueError('Conteúdo inesperado na tábua.')
    page.write_text(content[:match.start(2)] + text + content[match.end(2):], encoding='utf-8')
    print(f'Atualizado: {page} (anos: {", ".join(map(str, table["anos"]))})')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        sys.exit(f'Erro: {exc}')
