# ITSS Variant 9 Template

Шаблон учебного проекта по теме:

**Разработка системы интеллектуального управления пропускной способностью спутникового канала связи на основе прогнозирования трафика**

Репозиторий предназначен для передачи студентам как чистая рабочая основа. В нём оставлены только ключевые файлы проекта, итоговый ноутбук, документация и компактные reference-результаты.

## Структура

- `satellite_capacity_project.py` — основной скрипт проекта
- `notebooks/itss_variant_9_satellite_capacity.ipynb` — финальный ноутбук
- `docs/report.md` — отчёт
- `docs/presentation.md` — структура презентации
- `docs/speech.md` — текст выступления
- `docs/diagrams.md` — набор mermaid-схем
- `datasets/` — входные данные
- `results/` — ключевые итоговые графики и метрики

## Важно про датасет

Большой архив `ip_addresses_sample.tar` **не хранится в репозитории**, потому что он превышает лимит обычного GitHub.

Его нужно скачать отдельно и положить сюда:

```text
datasets/ip_addresses_sample.tar
```

Маленькие вспомогательные файлы уже включены:

- `datasets/times.tar`
- `datasets/weekends_and_holidays.csv`

## Откуда скачать большой архив

Используйте датасет `CESNET-TimeSeries24 sample` и скачайте архив `ip_addresses_sample.tar` из Zenodo вручную. После скачивания просто поместите его в каталог `datasets/`.

Структура каталога `datasets/` должна быть такой:

```text
datasets/
├── ip_addresses_sample.tar
├── times.tar
└── weekends_and_holidays.csv
```

## Установка зависимостей

```bash
python3 -m pip install -r requirements.txt
```

## Запуск проекта

Из корня репозитория:

```bash
python3 satellite_capacity_project.py
```

Скрипт:

- загружает почасовые ряды из `CESNET sample`;
- формирует агрегированный ряд нагрузки канала;
- строит признаки без leakage;
- сравнивает `NaiveLastValue`, `SeasonalNaive24`, `OLSRegression`;
- выбирает лучшую модель;
- сравнивает baseline и adaptive policy;
- сохраняет результаты в `results/`.

## Как открыть ноутбук

Откройте файл:

```text
notebooks/itss_variant_9_satellite_capacity.ipynb
```

Ноутбук использует тот же код проекта и показывает чистый воспроизводимый пайплайн от загрузки данных до итоговых графиков.

## Что ожидается в results

В репозиторий уже включены reference-артефакты:

- `results/capacity_control_plot.png`
- `results/model_rmse_comparison.png`
- `results/model_metrics.csv`
- `results/policy_metrics.csv`
- `results/run_summary.json`

При повторном запуске проекта также могут быть сгенерированы промежуточные CSV, но они не входят в шаблон репозитория.

## Ключевая идея проекта

Прогноз трафика в этой работе используется не как самоцель, а как вход для управления ресурсом канала. Интеллектуальность системы проявляется в том, что прогноз нагрузки автоматически влияет на выделяемую пропускную способность и позволяет уменьшать перегрузки канала.

## Основные материалы

- [Отчёт](docs/report.md)
- [Презентация](docs/presentation.md)
- [Текст выступления](docs/speech.md)
- [Mermaid-схемы](docs/diagrams.md)

## Лицензия и публикация

- [LICENSE](LICENSE)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [PUBLISHING.md](PUBLISHING.md)
