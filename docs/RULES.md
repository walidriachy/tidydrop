# Rules & local AI guide

## Custom rules (`rules.yaml`)

Click **Edit rules...** from the TidyDrop tray/menu-bar icon to open your `rules.yaml` file. Changes reload automatically as soon as you save. If a typo is found, TidyDrop keeps using your last valid rules and notifies you what to fix.

```yaml
rules:
  - name: Bank statements
    when:
      extensions: [pdf]
      text_contains_any: [statement, "account number"]
    move_to: Documents/Bank/{year}

  - name: WeTransfer client files
    when:
      source_contains: wetransfer.com
    move_to: Transfers/{year}-{month}

  - name: Large video exports
    when:
      category: Videos
      min_size_mb: 2000
    move_to: Videos/Large
    expire_days: 60
```

### Filename template variables

Configure your naming pattern in **Settings → General → Name template**:

| Token | Meaning | Example |
|---|---|---|
| `{date}` | Capture, document, or download date | `2026-11-20` |
| `{title}` | Clean title (from metadata or local AI) | `Adobe Creative Cloud Invoice` |
| `{extra}` | Media details such as resolution & length | `1080p 3min` |
| `{source}` | Website domain the file came from | `adobe.com` |
| `{category}` | Matched folder category | `Documents` |
| `{original}` | Original base filename | `scan0001` |

Default date format: `%Y-%m-%d`.

## Optional local AI renaming (Ollama)

TidyDrop can ask a local Ollama model to suggest clean titles for vague documents such as `scan0001.pdf` or `Document (3).docx`. **Your files never leave your computer.**

1. Download and install [Ollama](https://ollama.com).
2. Download a compact, fast model in Terminal / PowerShell:
   ```bash
   ollama pull llama3.2
   ```
3. Open TidyDrop **Settings → AI renaming**.
4. Enable **Use AI to name documents**, click **Find models**, select `llama3.2`, and click **Test with a sample invoice**.
