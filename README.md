# Claude Daily

Newsletter diária sobre o **Claude AI** — dicas, hacks, plugins, MCPs e novidades — vasculhada todo dia em blogs, Substacks, YouTube e GitHub, e publicada estaticamente no GitHub Pages.

## Como funciona

```
┌─────────────────┐   cron diário   ┌──────────────────┐   commit    ┌──────────────────┐
│ data/sources    │ ──────────────▶ │ scripts/build    │ ──────────▶ │ data/feed.json   │
│      .json      │                 │   _feed.py       │             │   (nova edição)  │
└─────────────────┘                 └──────────────────┘             └──────────────────┘
                                                                              │
                                                                              ▼
                                                                     ┌──────────────────┐
                                                                     │  index.html      │
                                                                     │  (GitHub Pages)  │
                                                                     │  faz fetch       │
                                                                     └──────────────────┘
```

1. **GitHub Action** roda às 09:00 BRT (12:00 UTC) todos os dias
2. O script lê `data/sources.json`, vasculha cada feed RSS, filtra por relevância (Claude/Anthropic/MCP/etc), classifica em categorias e seleciona os 12 melhores
3. Sobrescreve `data/feed.json` e arquiva a edição anterior em `data/archive/`
4. Dá push de volta no repositório
5. GitHub Pages serve o `index.html`, que carrega o `data/feed.json` via fetch

## Deploy (5 minutos)

### 1. Criar o repositório

Crie um repo público no GitHub chamado `claude-daily` (ou outro nome — só lembre de ajustar a URL final).

### 2. Subir os arquivos

```bash
cd claude-daily
git init
git add .
git commit -m "init: claude daily"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/claude-daily.git
git push -u origin main
```

### 3. Ativar o GitHub Pages

No repositório, vá em **Settings → Pages**:

- **Source:** Deploy from a branch
- **Branch:** `main` / `/ (root)`
- Salve

Em ~1 minuto o site fica online em `https://SEU-USUARIO.github.io/claude-daily/`.

### 4. Permitir que o Action escreva no repo

**Settings → Actions → General → Workflow permissions:**

- Marque **Read and write permissions**
- Salve

Sem isso, o bot não consegue dar push do feed atualizado.

### 5. Rodar manualmente pela primeira vez (opcional)

Aba **Actions → Build Daily Feed → Run workflow**.

Depois disso, ele roda sozinho todo dia.

## Personalizar fontes

Edite `data/sources.json`. Cada fonte tem:

```jsonc
{
  "name": "Nome legível",
  "url": "https://exemplo.com/feed.xml",
  "weight": 7,                          // 1-10: maior = aparece primeiro
  "filter_keywords": ["claude", "mcp"], // opcional: só pega itens que batem
  "default_category": "Dica"            // se nenhuma regra de categorização bater
}
```

Categorias usadas pelo front: `Dica`, `Hack`, `Plugin`, `MCP`, `Novidade`, `Video`.

## Personalizar visual

Tudo no `<style>` do `index.html`. A cor laranja é `--orange: #f1613a` — troque ali e propaga.

Fontes via Google Fonts:
- **Fraunces** (display, serifa) — headlines e números
- **Inter Tight** — texto corrido
- **JetBrains Mono** — labels, datas, categorias

## Rodar local (debug)

```bash
pip install -r scripts/requirements.txt
python scripts/build_feed.py

# servir o HTML
python -m http.server 8000
# abrir http://localhost:8000
```

## Estrutura

```
claude-daily/
├── index.html              # Página única (lê data/feed.json via fetch)
├── data/
│   ├── feed.json           # Edição atual (regerada todo dia)
│   ├── sources.json        # Lista mestre de RSS/feeds
│   └── archive/            # Edições anteriores arquivadas
├── scripts/
│   ├── build_feed.py       # Coletor + curador
│   └── requirements.txt
└── .github/workflows/
    └── daily-feed.yml      # Cron diário
```

## Licença

MIT. Conteúdo linkado pertence aos autores originais.
