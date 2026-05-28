# Использование

Требуется заранее установленный [Python 3.12](https://www.python.org/downloads/release/python-31213/).

```bash
git clone https://github.com/vmgorelikov/Automated-Classification-of-Language-Eloquent-Areas-in-Neurotypical-Individuals.git

cd Automated-Classification-of-Language-Eloquent-Areas-in-Neurotypical-Individuals

python -m venv .venv

.venv/Scripts/activate

pip install -r requirements.txt

cd src

python main.py путь_ко_входному_файлу.xlsx

```

Входной файл должен иметь единственный лист со столбцами, названными `RT_start` (время начала ответа), `Stimulus` (стимул) и `Response_annot` (орфографическая запись ответа).

В каталоге входного файла появится файл с предсказаниями.

# Структура репозитория

`src/` Исходный код.
+ `feature_extractor.py` Извлекатель признаков.
+ `main.py` Пользовательский интерфейс.

`data/` Данные.
+ `transcribed/` Исходные данные экспериментов[^1].
+ `processed/` Очищенные данные экспериментов[^1].
+ `ruwordnet/` Данные [RuWordNet](https://www.ruwordnet.ru/).
  + `polars_edges_dataframe.joblib.xz` Рёбра RuWordNet.
  + `polars_word_mapping_dataframe.joblib.xz` Словник, ставящий по взаимное соответствие ID вершин и слова в RuWordNet.
+ `word_frequencies/` Частотные списки слов.
  + `AranRusi_a.tsv` Частотный список слов из [Araneum Russicum Maximum](http://aranea.juls.savba.sk/aranea/run.cgi/corp_info?corpname=AranRusi_a).
+ `models/` Всё, что связано с работой непосредственно классификаторов.

`notebooks/` Тетради, использовавшиеся при выполнении работы.
+ `dataset_preparation.ipynb` Подготовка датасета.
+ `dataset_split.ipynb` Разбиение датасета.
+ `feature_extraction.ipynb` Извлечение признаков (черновая).
+ `feature_and_model_selection.ipynb` Выбор модели и признаков.
+ `final_evaluations.ipynb` Окончательная оценка моделей на тестовой выборке.

[^1]: Набор данных экспериментов с ТМС для выполнения работы был получен на условиях нераспространения.
