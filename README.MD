# Использование

Требуется заранее установленный Python 3.12

```bash
git clone https://github.com/vmgorelikov/Automated-Classification-of-Language-Eloquent-Areas-in-Neurotypical-Individuals.git

cd Automated-Classification-of-Language-Eloquent-Areas-in-Neurotypical-Individuals

python -m venv .venv

pip install -r requirements.txt

cd src

python main.py путь_ко_входному_файлу.xlsx

```

Входной файл должен быть в формате Office Open XML SpreadsheetML (.xlsx) иметь единственный лист со столбцами, названными `RT_start` (время начала ответа), `Stimulus` (стимул) и `Response_annot` (орфографическая запись ответа).

В каталоге `output` появится выходной файл с предсказаниями классов.

Набор данных для выполнения работы был получен на условиях нераспространения.

# Структура репозитория

`src/` — исходный код прикладного результата.
`data/` — данные, необходимые для функционирования прикладного результата (частотный список, данные машиночитаемого словаря и проч.)
`notebooks/` — черновые тетради, использовавшиеся для выполнения работы.
`paper/` — не используется.
