# Деплой на сервер (Hetzner) — покроково для початківців

Тут описано **найпростіший шлях**: сервер у Hetzner, код **завантажуєте з GitHub прямо на сервер** (`git clone`), далі запуск через **Docker**. Нічого зайвого.

---

## Що ви взагалі робите

1. Берете **віртуальний сервер** (VPS) в інтернеті — наприклад у [Hetzner](https://www.hetzner.com/cloud).
2. **Підключаєтесь** до нього зі свого комп’ютера через **SSH** (текстова консоль у терміналі).
3. На сервері **клонуєте репозиторій з GitHub** — це як «завантажити проєкт однією командою».
4. Запускаєте програму в **Docker** — щоб не ставити Python і залежності вручну.

Так, **стягнути код з GitHub на сервер можна і так зазвичай і роблять.** Потрібен лише **публічний репозиторій** або **приватний** + доступ (ключ або токен) — про це нижче.

---

## Крок 0. Перед початком (на своєму ПК)

Запишіть собі:

| Що | Навіщо |
|----|--------|
| **IP-адреса сервера** | Hetzner показує її після створення VPS (наприклад `95.xxx.xxx.xxx`) |
| **Пароль root** або **SSH-ключ** | Щоб зайти на сервер першого разу |
| **Посилання на ваш GitHub-репо** | Кнопка зелена **Code** на GitHub → HTTPS, наприклад `https://github.com/ваш-логін/Practice.git` |

**Де саме лежить папка `backend` у репо:** якщо весь проєкт у корені репо, після клонування шлях буде `Practice/backend` (або як у вас назва папки). Далі всі команди виконуєте **з папки `backend`**, де лежать `Dockerfile` і `docker-compose.yml`.

Якщо репозиторій **приватний**, GitHub на сервері попросить логін. Зручніше зробити **Personal Access Token** (GitHub → Settings → Developer settings → Tokens) і замість пароля вставляти токен. Або налаштувати **SSH-ключ** на сервері й клонувати через `git@github.com:...`.

---

## Крок 1. Зайти на сервер по SSH

На **Windows** у PowerShell або CMD (або встановіть [Windows Terminal](https://github.com/microsoft/terminal)):

```bash
ssh root@ВАШ_IP
```

Підставте замість `ВАШ_IP` реальну адресу. Перше підключення запитає «trust this host» — наберіть `yes`. Пароль — той, що дав Hetzner (або використовується ключ).

Якщо заходите не під `root`, а під користувача `ubuntu` / `admin` — команда може бути така:

```bash
ssh ubuntu@ВАШ_IP
```

Далі всі наступні команди виконуєте **у вже відкритій сесії SSH** (ви «всередині» сервера).

---

## Крок 2. Оновити систему і встановити Docker

На сервері (Ubuntu/Debian це найчастіше):

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
```

Перевірка, що Docker є:

```bash
sudo docker --version
```

Якщо `docker compose` не знайдено, спробуйте:

```bash
sudo docker compose version
```

(Плагін ставиться разом із `docker-compose-plugin`.)

---

## Крок 3. Сягнути проєкт з GitHub

Створіть папку і перейдіть у неї (назви можете змінити):

```bash
mkdir -p ~/apps
cd ~/apps
```

**Клонування** (підставте **своє** посилання з GitHub):

```bash
git clone https://github.com/ВАШ_ЛОГІН/ВАШ_РЕПО.git
cd ВАШ_РЕПО
```

Якщо у репо є вкладена папка `backend`:

```bash
cd backend
```

Переконайтеся, що тут є файли `Dockerfile` і `docker-compose.yml`:

```bash
ls -la
```

Якщо пізніше оновите код на GitHub, на сервері достатньо зайти в ту саму папку і виконати:

```bash
git pull
```

Потім знову зібрати й перезапустити контейнер (крок 6).

---

## Крок 4. Створити `.env` і `channels.txt`

У папці `backend` (де `docker-compose.yml`):

```bash
cp .env.example .env
nano .env
```

У `nano`: відредагуйте що потрібно (ключі стріму тощо), збережіть — **Ctrl+O**, Enter, вийти — **Ctrl+X**.

Якщо файлу каналів ще немає:

```bash
touch channels.txt
```

(Це важливо для Docker: інакше може створитись «папка» замість файлу.)

---

## Крок 5. Перший запуск

```bash
sudo docker compose up -d --build
```

- `-d` — працює у фоні  
- `--build` — зібрати образ з `Dockerfile`

Подивитись логи:

```bash
sudo docker compose logs -f
```

Вийти з перегляду логів: **Ctrl+C** (контейнер не зупиниться).

---

## Крок 6. Перевірити, що все живе

На **самому сервері**:

```bash
curl -s http://127.0.0.1:8765/health
```

Має з’явитись щось на кшталт `{"status":"ok"}`.

Адмінка за замовчуванням слухає **лише localhost** (це добре для безпеки). Подивитись її зі свого **домашнього** комп’ютера можна через **SSH-тунель**.

На **вашому ПК** (новий термінал, не закриваючи сесію до сервера):

```bash
ssh -L 8765:127.0.0.1:8765 root@ВАШ_IP
```

Потім у браузері відкрийте: **http://127.0.0.1:8765/**

Поки це вікно SSH відкрите — тунель працює.

---

## Публічний доступ у браузері (без SSH-тунелю)

Ідея: **контейнер лишається на `127.0.0.1:8765`** (як у `docker-compose.yml`) — у інтернет дивиться лише **nginx** на портах **80** (HTTP) і за бажанням **443** (HTTPS). Так роблять майже завжди.

### Крок 1 — nginx на сервері (SSH-сесія)

```bash
sudo apt update
sudo apt install -y nginx
```

Переконайтеся, що контейнер працює і відповідає локально:

```bash
curl -s http://127.0.0.1:8765/health
```

### Крок 2 — два варіанти

#### Варіант A: є домен (бажано: HTTPS)

1. У панелі DNS домену додайте запис типу **A**: ім’я (наприклад `radio` або `@`) → **IP вашого сервера** (наприклад `164.90.174.228`). Зачекайте 5–30 хвилин.

2. Скопіюйте приклад і вкажіть свій домен:

```bash
sudo nano /etc/nginx/sites-available/mediahub
```

Вставте вміст з файлу репо `deploy/nginx-mediahub.conf`, замініть `ваш.домен.example` на реальний (наприклад `radio.example.com`).

3. Увімкніть сайт і перевірте конфіг:

```bash
sudo ln -sf /etc/nginx/sites-available/mediahub /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

4. Відкрийте firewall і встановіть сертифікат:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo ufw allow 'Nginx Full'
sudo ufw reload
sudo certbot --nginx -d ваш.піддомен.домен
```

5. У браузері відкривайте **https://ваш.піддомен.домен**

#### Варіант B: без домену — лише IP (HTTP, без шифрування)

Підійде для тесту. **Паролі та ключі в адмінці йдуть відкритим текстом** — для реального ефіру краще зробити домен + HTTPS (варіант A).

```bash
cd ~/apps/Practice
# якщо deploy/ лежить у корені репо (поруч із docker-compose.yml):
sudo cp deploy/nginx-mediahub-ip.conf /etc/nginx/sites-available/mediahub
sudo ln -sf /etc/nginx/sites-available/mediahub /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow 80/tcp
sudo ufw reload
```

У браузері: **http://ВАШ_IP** (наприклад `http://164.90.174.228`).

Якщо сторінка не відкривається — у панелі **DigitalOcean** (Networking → Firewall) переконайтеся, що для droplet дозволені вхідні **80** (і для HTTPS — **443**).

### Важливо про безпеку

- Адмінка **не має вбудованого логіну** — будь-хто з лінком може керувати ефіром. Для публічного IP або домену варто додати **обмеження по IP** у nginx, **basic auth**, або Cloudflare Access — це вже окреме налаштування.
- Після переходу на nginx **тунель SSH для порту 8765 не обов’язковий** — заходите напряму по домену/IP.

---

## Що робити далі (коли освоїтесь)

- **Бекап** даних (черга, стан) — том Docker `mediahub_state`; його можна періодично копіювати.

---

## Якщо щось пішло не так

| Проблема | Що спробувати |
|----------|----------------|
| `git clone` просить логін / ні Privat | Для приватного репо потрібен токен GitHub або SSH-ключ |
| `docker compose` not found | Встановіть `docker-compose-plugin`, використовуйте `sudo docker compose` |
| Порт зайнятий | Змініть у `.env` `MEDIAHUB_ADMIN_PORT` і в `docker-compose.yml` мапінґ порту |
| Немає `backend` після clone | Перевірте структуру репо на GitHub; `cd` у правильну папку |

---

## Коротко: чи можна з GitHub на сервері?

**Так.** Алгоритм такий: **SSH на сервер → `git clone` → `cd` у `backend` → `.env` + `touch channels.txt` → `sudo docker compose up -d --build`.**

Оновлення коду: **`git pull`** у тій самій папці, потім перезбірка/перезапуск контейнера.
