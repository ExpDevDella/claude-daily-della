#!/usr/bin/env python3
"""
build_feed.py
Vasculha as fontes em data/sources.json, pega os itens mais recentes
sobre Claude / Anthropic / MCP / etc, e gera data/feed.json com a edição do dia.

Roda todo dia via GitHub Actions.
"""

import json
import os
import re
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import feedparser

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SOURCES_FILE = DATA_DIR / "sources.json"
FEED_FILE = DATA_DIR / "feed.json"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

# Fuso de Brasília
BRT = timezone(timedelta(hours=-3))

# Palavras-chave que indicam relevância pro mundo Claude
RELEVANCE_KEYWORDS = [
    "claude", "anthropic", "mcp", "model context protocol",
    "opus", "sonnet", "haiku", "claude code", "cowork",
    "claude.md", "claude desktop", "claude api"
]

# Padrões que indicam título-lixo (commit, CI noise, etc) — descartamos
JUNK_PATTERNS = [
    r"^merge pull request",
    r"^merge branch",
    r"^update.*progress",
    r"^chore\(",
    r"^chore:",
    r"^bump\s",
    r"^\[skip ci\]",
    r"\[skip ci\]",
    r"^wip[\s:]",
    r"^fix typo",
    r"^add .{1,12}$",   # "add Foo" muito curto
]

MAX_ITEMS_PER_EDITION = 12
MAX_ITEMS_PER_SOURCE = 3
MIN_TITLE_LENGTH = 25  # títulos muito curtos costumam ser ruim


def is_junk(title: str) -> bool:
    """Identifica títulos lixo que não viram boa newsletter."""
    if len(title.strip()) < MIN_TITLE_LENGTH:
        return True
    t = title.lower()
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


def is_relevant(text: str, extra_filters=None) -> bool:
    """Retorna True se o texto contém alguma palavra-chave relevante."""
    text_lower = text.lower()
    keywords = RELEVANCE_KEYWORDS[:]
    if extra_filters:
        keywords = extra_filters  # filtros específicos da fonte sobrescrevem
    return any(kw in text_lower for kw in keywords)


def categorize(title: str, summary: str, link: str, rules: dict, default: str) -> str:
    """Classifica o item em uma categoria com base nas regras."""
    text = f"{title} {summary} {link}".lower()
    for category, patterns in rules.items():
        for p in patterns:
            if p.lower() in text:
                return category
    return default


def clean_summary(raw: str, max_len: int = 240) -> str:
    """Remove HTML do summary e trunca."""
    if not raw:
        return ""
    # remove tags HTML
    text = re.sub(r"<[^>]+>", " ", raw)
    # normaliza espaços
    text = re.sub(r"\s+", " ", text).strip()
    # remove entidades comuns
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def parse_date(entry) -> datetime:
    """Tenta extrair a data do entry, retorna agora se não conseguir."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(field)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(tz=timezone.utc)


def item_id(url: str) -> str:
    """ID estável pro item a partir da URL."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def fetch_source(source: dict, categorization_rules: dict) -> list:
    """Vasculha uma fonte e retorna lista de itens normalizados."""
    print(f"  → {source['name']}", flush=True)
    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        print(f"    erro: {e}", flush=True)
        return []

    items = []
    extra_filters = source.get("filter_keywords")
    default_cat = source.get("default_category", "Dica")

    for entry in feed.entries[:20]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        # filtra lixo de commit/CI
        if is_junk(title):
            continue

        summary = clean_summary(entry.get("summary", "") or entry.get("description", ""))
        haystack = f"{title} {summary}"

        # Filtra por relevância
        if extra_filters:
            # fonte tem filtros próprios — só passa se bater
            if not is_relevant(haystack, extra_filters):
                continue
        else:
            # fonte é dedicada (ex: Anthropic) — assume relevante
            pass

        category = categorize(title, summary, link, categorization_rules, default_cat)
        published = parse_date(entry)

        items.append({
            "id": item_id(link),
            "title": title,
            "summary": summary or "Sem resumo disponível.",
            "url": link,
            "source": source["name"],
            "category": category,
            "weight": source.get("weight", 5),
            "published": published.isoformat(),
            "_published_dt": published,
        })

    # Limita por fonte
    items.sort(key=lambda x: x["_published_dt"], reverse=True)
    return items[:MAX_ITEMS_PER_SOURCE]


def load_seen_ids() -> set:
    """Carrega IDs de itens que já apareceram nas últimas 5 edições."""
    seen = set()
    archives = sorted(ARCHIVE_DIR.glob("*.json"), reverse=True)[:5]
    for arch in archives:
        try:
            data = json.loads(arch.read_text(encoding="utf-8"))
            for item in data.get("items", []):
                if "id" in item:
                    seen.add(item["id"])
        except Exception:
            pass
    return seen


def get_next_issue_number() -> int:
    """Calcula o número da próxima edição baseado no feed atual."""
    if FEED_FILE.exists():
        try:
            data = json.loads(FEED_FILE.read_text(encoding="utf-8"))
            return int(data.get("issue", 0)) + 1
        except Exception:
            pass
    return 1


def main():
    sources_data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    sources = sources_data["feeds"]
    rules = sources_data.get("categorization_rules", {})

    print(f"Vasculhando {len(sources)} fontes…", flush=True)
    all_items = []
    for src in sources:
        all_items.extend(fetch_source(src, rules))

    print(f"\nTotal coletado: {len(all_items)} itens", flush=True)

    # Remove duplicatas pelo ID
    by_id = {}
    for item in all_items:
        if item["id"] not in by_id:
            by_id[item["id"]] = item
        else:
            # mantém o de maior peso
            if item["weight"] > by_id[item["id"]]["weight"]:
                by_id[item["id"]] = item

    unique_items = list(by_id.values())
    print(f"Únicos: {len(unique_items)}", flush=True)

    # Remove itens que já foram destaque em edições recentes
    seen = load_seen_ids()
    fresh = [i for i in unique_items if i["id"] not in seen]
    print(f"Frescos (não repetidos): {len(fresh)}", flush=True)

    # Se sobrou muito pouco fresco, complementa com os melhores que já apareceram
    if len(fresh) < MAX_ITEMS_PER_EDITION:
        backups = [i for i in unique_items if i["id"] in seen]
        backups.sort(key=lambda x: (x["weight"], x["_published_dt"]), reverse=True)
        fresh.extend(backups[: MAX_ITEMS_PER_EDITION - len(fresh)])
        print(f"Complementado com {len(backups[: MAX_ITEMS_PER_EDITION - len(fresh)])} backups", flush=True)

    # Ordena por peso da fonte + data
    fresh.sort(key=lambda x: (x["weight"], x["_published_dt"]), reverse=True)
    final_items = fresh[:MAX_ITEMS_PER_EDITION]

    # Marca o primeiro como featured
    if final_items:
        final_items[0]["featured"] = True

    # Limpa campos internos
    for it in final_items:
        it.pop("_published_dt", None)

    if not final_items:
        print("ERRO: nenhum item coletado. Mantendo feed.json anterior.", flush=True)
        sys.exit(0)

    # Salvaguarda: se a coleta veio fraca (< 5 itens), preserva o feed anterior
    # para evitar uma edição ruim no ar.
    MIN_VIABLE_ITEMS = 5
    if len(final_items) < MIN_VIABLE_ITEMS and FEED_FILE.exists():
        print(f"⚠ Apenas {len(final_items)} itens coletados (mínimo {MIN_VIABLE_ITEMS}). Mantendo feed anterior.", flush=True)
        sys.exit(0)

    now = datetime.now(tz=BRT)
    edition = {
        "issue": get_next_issue_number(),
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "items": final_items,
    }

    # Arquiva edição atual antes de sobrescrever
    if FEED_FILE.exists():
        try:
            prev = json.loads(FEED_FILE.read_text(encoding="utf-8"))
            prev_date = prev.get("date", "unknown")
            prev_issue = prev.get("issue", 0)
            archive_path = ARCHIVE_DIR / f"{prev_date}-issue-{prev_issue:03d}.json"
            archive_path.write_text(
                json.dumps(prev, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"Edição anterior arquivada em: {archive_path.name}", flush=True)
        except Exception as e:
            print(f"Falha ao arquivar: {e}", flush=True)

    FEED_FILE.write_text(
        json.dumps(edition, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n✓ Edição #{edition['issue']} de {edition['date']} gerada com {len(final_items)} itens.", flush=True)


if __name__ == "__main__":
    main()
