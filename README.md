# 🤖 Antigravity Liquidity Sweep Trading Bot v2.0

Автономная торговая система для бессрочных фьючерсов Bybit V5 USDT-M, основанная на стратегии снятия пулов ликвидности (**Liquidity Sweep & Reclaim**), динамическом риск-менеджменте и интерактивном управлении через Telegram-бота (**@Leekvid_bot**).

---

## 🏛 Архитектура системы

```
02antigravity-trading-bot/
├── main.py              # Точка входа: backtest / generate / live
├── config.py            # Конфигурация Pydantic Settings (.env)
├── database.py          # SQLite ORM: таблицы trades, bot_settings (data/antigravity.db)
├── telegram_bot.py      # Telegram UI: интерактивное меню, callback-кнопки, Panic-mode
├── strategy_engine.py   # Алгоритм снятия пулов ликвидности (Sweep & Reclaim)
├── execution_engine.py  # Модели исполнения: Live Bybit V5 & Simulated Dry-Run
├── risk_manager.py      # Динамический расчет плеча и размера позиции (2% риск-кап)
├── data_ingestion.py    # Загрузка 15m свечей, расчет VWAP, SMA20, volume ratio
├── market_simulator.py  # Генератор синтетических ценовых траекторий
├── stress_tester.py     # Движок хронологического бэктеста и стресс-тестирования
├── simulate_7d.py       # Скрипт 7-дневной исторической симуляции (BTC, ETH, SOL)
├── visualizer.py        # Отрисовка кривой доходности и просадок
├── Dockerfile           # Контейнеризация Python 3.11-slim
├── docker-compose.yml   # Запуск изолированного сервиса
├── run.ps1              # Быстрый запуск на Windows 11 PowerShell
├── deploy.sh            # Скрипт развертывания на Linux VPS
├── .env.example         # Шаблон переменных окружения
├── requirements.txt     # Зависимости Python
└── tests/               # Автоматический тестовый шлюз (100% Green Pytest Gate)
    ├── test_risk.py
    └── test_strategy.py
```

---

## 🚀 Инструкция по развертыванию на новом ПК

### Вариант 1. Локальный запуск на Windows (PowerShell)

#### Требования:
* Python 3.10, 3.11 или выше
* Git

#### Шаги:
1. **Клонировать репозиторий:**
   ```powershell
   git clone https://github.com/JariusS/lekvid.git
   cd lekvid
   ```

2. **Создать и активировать виртуальное окружение:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Установить зависимости:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Настроить конфигурацию `.env`:**
   ```powershell
   Copy-Item .env.example .env
   ```
   Откройте `.env` и укажите ваши ключи:
   ```ini
   BYBIT_API_KEY="ваш_api_ключ"
   BYBIT_API_SECRET="ваш_api_секрет"
   BYBIT_TESTNET="False"

   TELEGRAM_BOT_TOKEN="8790172377:AAHM2B-_S30nPs4qRY56LvL1UKxBgcgyPwM"
   TELEGRAM_CHAT_ID="462405927"
   ```

5. **Запуск тестов pre-flight:**
   ```powershell
   python -m pytest tests/ -v
   ```

6. **Быстрый старт (или через `.\run.ps1`):**
   ```powershell
   # Режим симуляции (Dry-Run, без риска):
   python main.py --mode live --dry-run --symbol BTCUSDT

   # Режим реальной торговли Bybit Perpetual Futures:
   python main.py --mode live --symbol BTCUSDT
   ```

---

### Вариант 2. Развертывание на Linux / VPS (Docker)

1. **Клонировать репозиторий:**
   ```bash
   git clone https://github.com/JariusS/lekvid.git
   cd lekvid
   ```

2. **Создать `.env`:**
   ```bash
   cp .env.example .env
   nano .env
   ```

3. **Запустить контейнер через Docker Compose:**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```
   Или напрямую:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

---

## 📱 Управление через Telegram (@Leekvid_bot)

Бот поддерживает интерактивное управление через клавиатуру `ReplyKeyboardMarkup`:

| Кнопка | Действие |
|---|---|
| `💼 Открытые сделки` | Список активных позиций, текущий PnL, прогресс-бар движения к TP1 и Inline-кнопки (`🛡 В безубыток`, `🎯 Забрать 50%`, `❌ Закрыть позицию`, `📈 График Bybit`). |
| `💰 Баланс` | Просмотр кошелька, доступного баланса и PnL за текущий день. |
| `📊 Статистика` | Общий профит, WinRate %, количество закрытых трейдов, лучший/худший результат. |
| `🏆 Топ монет` | Мониторинг ключевых пар (BTCUSDT, ETHUSDT, SOLUSDT). |
| `⚙️ Настройки` | Переключение режимов: `АВТО`, `Только LONG`, `Только SHORT`, `Пауза/Старт`. |
| `🚨 Закрыть всё` | Panic Button — закрывает все активные позиции по рынку и ставит сканер на паузу (с подтверждением). |
| `🔄 Синхронизация Sheets` | Статус синхронизации локальной базы SQLite. |
| `⚙️ Статус` | Текущий режим работы, статус сканера и рабочая пара. |

---

## 🧪 Запуск симуляций и бэктестов

1. **7-дневный исторический бэктест по основным 3 криптовалютам (BTC, ETH, SOL):**
   ```bash
   python simulate_7d.py
   ```

2. **Синтетический стресс-тест в экстремальных рыночных режимах (flash-crash, sideways, bullish):**
   ```bash
   python main.py --mode generate --regime flash_crash
   ```

3. **Полноценный бэктест стратегии:**
   ```bash
   python main.py --mode backtest --symbol BTCUSDT --timeframe 15m
   ```

---

## 🛡 Безопасность
* Файлы `.env`, приватные SSH/API ключи, базы данных `*.db` и кэши находятся в `.gitignore` и **никогда не попадают в систему контроля версий**.
* Пре-флайт тесты запускаются перед каждым запуском боевого торгового контура. При непрохождении хотя бы одного теста исполнение аварийно прерывается (`TestingFailedError`).