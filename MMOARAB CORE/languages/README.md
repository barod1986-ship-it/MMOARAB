# MMOARAB Core - Translation Files

## 📁 Files

- **mmoarab-core.pot** - Translation template file
- **mmoarab-core-ar.po** - Arabic translation file (editable)
- **mmoarab-core-ar.mo** - Arabic compiled translation (binary)

---

## 🔧 How to Compile PO to MO

### Method 1: Using Poedit (Recommended)
1. Download and install [Poedit](https://poedit.net/)
2. Open `mmoarab-core-ar.po` in Poedit
3. Make your changes (if needed)
4. Save the file - Poedit will automatically generate the `.mo` file

### Method 2: Using Command Line (msgfmt)
```bash
msgfmt mmoarab-core-ar.po -o mmoarab-core-ar.mo
```

### Method 3: Using WordPress Plugin
Install **Loco Translate** plugin from WordPress dashboard and manage translations through the UI.

---

## 🌍 Adding New Languages

1. Copy `mmoarab-core-ar.po` to `mmoarab-core-{locale}.po`
   - Example: `mmoarab-core-en_US.po` for English
   - Example: `mmoarab-core-fr_FR.po` for French

2. Edit the new `.po` file with your translations

3. Compile to `.mo` using one of the methods above

---

## 📝 Translation Coverage

✅ **Fully Translated:**
- Custom Post Type (Game)
- All Taxonomies (Type, Status, Platform, Mode, Engine)
- Meta Boxes (Information, Gallery, Features, Ratings)
- Single Game Template
- Archive Template
- Admin Pages
- Related Posts

---

## 🎯 Current Languages

| Language | Code | Status |
|----------|------|--------|
| Arabic   | ar   | ✅ Complete |
| English  | en_US | 🔄 Template Only |

---

## 🔄 Updating Translations

When you update the plugin and add new translatable strings:

1. Update `mmoarab-core.pot` with new strings
2. Merge new strings into `mmoarab-core-ar.po`
3. Translate the new strings
4. Recompile to `.mo`

---

## 📌 Notes

- The plugin uses `mmoarab-core` as text domain
- All translatable strings use `__()`, `_e()`, `_n()` functions
- RTL support is built-in for Arabic
- Domain path: `/languages/`
