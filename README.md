# Jira Server 8.5.1 → MCP (только чтение)

MCP-сервер для чтения задач и проектов Jira Server 8.5.1. ChatGPT подключается по Streamable HTTP с OAuth.
В Compose входят MCP и Caddy с автоматическим HTTPS.

## Что потребуется

- Linux-сервер с Docker Engine и Docker Compose **2.30+** (используется `env_file.format: raw`).
- Свободные входящие TCP 80/443 и домен, например `jira-mcp.example.com`, с A-записью на сервер.
  Если существует AAAA-запись, она тоже должна вести на этот сервер; иначе удалите её.
- Исходящий доступ к Jira по HTTPS, GitHub OAuth/API, центру сертификации и реестрам образов/Python.
- Учётная запись Jira и GitHub. GitHub используется только для входа в MCP.
- Возможность добавить собственный MCP-сервер в ChatGPT. Todoist нужен только для примера переноса задач.

## 1. Подготовить настройки

Клонируйте репозиторий на сервер и создайте локальный `.env`:

```bash
git clone https://github.com/ildarikga/jira_mcp.git
cd jira_mcp
python3 init_env.py
chmod 600 .env
nano .env
```

`init_env.py` создаёт `.env` с двумя случайными ключами; существующий `.env` не перезаписывает.
Остальные значения заполните вручную:

| Переменная | Значение |
|---|---|
| `MCP_DOMAIN` | Домен без https и пути, например `jira-mcp.example.com` |
| `MCP_PUBLIC_URL` | `https://jira-mcp.example.com`, тот же домен, без пути |
| `ACME_EMAIL` | Ваш email для сертификата |
| `JIRA_BASE_URL` | URL вашей Jira с её контекстным путём, например `https://jira.example.com/jira` |
| `JIRA_USERNAME` | Логин Jira |
| `JIRA_PASSWORD` | Пароль Jira |
| `GITHUB_CLIENT_ID` | Client ID OAuth App, см. ниже |
| `GITHUB_CLIENT_SECRET` | Client Secret OAuth App |
| `GITHUB_ALLOWED_USER_ID` | Числовой ID вашего GitHub-пользователя |

Значения записываются **без обрамляющих кавычек**, в одну строку.
Для контейнера MCP используется raw env_file: символы `$`, `#`, кавычки внутри пароля сохраняются буквально.
Не запускайте `source .env`. Не публикуйте результат `docker compose config`: в нём могут быть секреты.

## 2. Создать GitHub OAuth App

Откройте https://github.com/settings/developers → **OAuth Apps → New OAuth App**.

- Application name: `Jira Read Only MCP`
- Homepage URL: `https://jira-mcp.example.com`
- Authorization callback URL: `https://jira-mcp.example.com/auth/callback`

Замените пример вашим доменом. Скопируйте Client ID и сгенерированный Client Secret в `.env`.

Числовой ID вашей учётной записи можно посмотреть по адресу
`https://api.github.com/users/YOUR_GITHUB_LOGIN` — поле `id`.
Это **ID пользователя**, не Client ID приложения и не GitHub-логин.

Вход разрешён только этому ID. Другой GitHub-пользователь не получает доступ к Jira.
Запрашивается `read:user`; доступ к репозиториям не запрашивается.
OAuth обслуживает FastMCP, включая регистрацию MCP-клиента, consent и PKCE.

## 3. Запустить

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 jira-mcp caddy
```

Проверки:

```bash
curl -fsS https://jira-mcp.example.com/healthz
curl -fsS https://jira-mcp.example.com/.well-known/oauth-authorization-server
curl -i https://jira-mcp.example.com/mcp
```

Ожидается: `{"status":"ok"}`, JSON OAuth metadata и `401` для `/mcp` без токена.
`healthz` проверяет работу процесса, **не** пароль Jira и **не** доступность Jira.
Порт 8000 не опубликован на хосте. Не добавляйте перед MCP обычную Nginx Basic Auth:
она помешает OAuth discovery. Публичный endpoint обслуживает Caddy.
Если 80/443 уже заняты, адаптируйте конфигурацию под существующий reverse proxy.
Проксировать нужно весь домен, включая `/.well-known/*`, `/auth/*` и OAuth endpoints;
для потокового MCP отключите буферизацию.

### Вариант: Nginx на другом хосте

Используйте отдельный `docker-compose.nginx.yml`: он запускает только MCP и публикует
порт 8000 на внутреннем IP сервера. Caddy в этом варианте не запускается.
В `.env` добавьте `MCP_BIND_IP` с внутренним IP сервера MCP и задайте
`MCP_PUBLIC_URL=https://ВАШ_ВНЕШНИЙ_ДОМЕН` без пути. `MCP_DOMAIN` и `ACME_EMAIL`
для этого варианта не используются. HTTPS и сертификат обслуживает внешний Nginx;
DNS домена должен вести на него. Callback в GitHub OAuth App:
`https://ВАШ_ВНЕШНИЙ_ДОМЕН/auth/callback`.

В HTTPS-блок выделенного домена на Nginx добавьте содержимое
`nginx-location.conf.example`. Замените `192.0.2.10` в `proxy_pass` на адрес из `MCP_BIND_IP`.
Конфигурация проксирует весь домен, включая `/mcp`, `/.well-known/*`, `/auth/*`
и остальные OAuth endpoints, с отключённой буферизацией и кешированием.
Не ограничивайте проксирование только путём `/mcp`.
Доступ к внутреннему порту 8000 разрешите только хосту Nginx средствами сети
или правилами, учитывающими опубликованные Docker-порты.

```bash
docker compose -f docker-compose.nginx.yml config --quiet
docker compose -f docker-compose.nginx.yml up -d --build
docker compose -f docker-compose.nginx.yml ps
docker compose -f docker-compose.nginx.yml logs --tail=100 jira-mcp
```

Используйте `-f docker-compose.nginx.yml` во всех командах Compose для этого варианта.
Проверки внешнего HTTPS-адреса остаются такими же, как выше.
Обычную Nginx Basic Auth перед MCP не добавляйте: доступ проверяет OAuth сервера.

## 4. Подключить в ChatGPT

По актуальной документации OpenAI:

1. Откройте https://chatgpt.com/plugins в веб-интерфейсе.
2. Нажмите **+ → Add custom MCP server** (названия могут отличаться в вашей версии интерфейса).
3. Укажите имя `Jira Read Only` и Server URL: `https://jira-mcp.example.com/mcp`.
4. Выберите **OAuth**. Если интерфейс предлагает DCR, используйте DCR.
   Client ID / Secret GitHub не вводите в ChatGPT: они предназначены серверу.
   Для MCP-клиента используется автоматическая регистрация (DCR), CIMD здесь отключён.
5. Создайте и установите плагин, подключите его, войдите через разрешённый GitHub-аккаунт.
6. Выберите плагин через `@` в разговоре и проверьте получение задач.

Доступ зависит от возможностей аккаунта, разрешений рабочей области и ограничений безопасности.
Если пункта добавления своего MCP нет, сначала решите вопрос с доступностью этой функции;
отключать авторизацию сервера для обхода не нужно.

Пример первой команды:

> Используй Jira Read Only. Покажи все мои незакрытые задачи, следуя next_start_at до конца. В Todoist ничего не добавляй.

Дальше, когда чтение проверено:

> Получи все мои незакрытые задачи Jira. Сравни с Todoist и добавь отсутствующие в указанный мной проект, сохранив ключ и ссылку Jira. Не изменяй Jira.

Сам MCP не обращается к Todoist и не запускает синхронизацию по расписанию.

## Учётная запись Jira и значение «мои»

**`currentUser()` — это пользователь из `JIRA_USERNAME`, а не GitHub и не текущий пользователь ChatGPT.**
Если указать вашу Jira-учётную запись, `jira_get_my_issues` вернёт ваши задачи.
Если указать отдельную техническую учётную запись, используйте `jira_search_issues` с явным JQL:

```jql
assignee = "your.jira.login" AND resolution = Unresolved ORDER BY updated DESC
```

Права Jira определяют видимые проекты и задачи. Код ограничивает запросы чтением;
для дополнительного ограничения учётной записи в Jira оставьте только нужные права просмотра.
Все разрешённые клиенты MCP используют одну настроенную учётную запись Jira.

## Инструменты

| Инструмент | Назначение |
|---|---|
| `jira_get_my_issues(start_at=0, max_results=50)` | Незакрытые задачи настроенного Jira-пользователя |
| `jira_search_issues(jql, start_at=0, max_results=50)` | Поиск по JQL |
| `jira_get_issue(issue_key)` | Поля задачи и описание (до 30 000 символов) |
| `jira_get_projects()` | Доступные проекты |
| `jira_get_transitions(issue_key)` | Просмотр возможных переходов, без выполнения |

Поиск возвращает `total`, `start_at`, `next_start_at` и `issues`.
Размер страницы 1–100. Для полного списка продолжайте с `next_start_at` до `null`.
«Незакрытые» определяются `resolution = Unresolved`, что зависит от заполнения resolution в workflow Jira.
Комментарии, вложения и произвольные REST endpoints не экспортируются.

## Ограничения и эксплуатация

- Все исходящие запросы к Jira — GET по фиксированному списку REST API v2 endpoints.
- Проверка TLS включена, редиректы Jira не выполняются.
- Даже при ошибке разрешений MCP не раскрывает тело ответа Jira и секреты.
- OAuth-данные хранятся зашифрованными в volume `oauth_data`; ключи — в `.env`.
- Сохраняйте `.env` и volumes для переживания пересоздания контейнеров.
  `docker compose down` сохраняет volumes; `down -v` удаляет OAuth-данные и сертификаты.
- Для обновления секретов используйте `docker compose up -d --force-recreate jira-mcp`.
  При смене OAuth-ключей может потребоваться повторное подключение ChatGPT.
- Тексты задач поступают в ChatGPT по запросу. Содержимое задач рассматривается как данные,
  а не команды. Сам сервер не исполняет текст задач.
- OAuth GitHub требует доступности GitHub со стороны сервера и браузера.

## Диагностика

| Симптом | Что проверить |
|---|---|
| Не выпускается сертификат | A/AAAA, входящие 80/443, занятые порты |
| HTTP 401 от Jira | Логин/пароль, блокировку учётной записи или CAPTCHA после ошибок входа |
| HTTP 403/404 от Jira | Права Browse Projects, issue security и ключ задачи |
| HTTP 400 при поиске | Синтаксис JQL и имена полей/пользователей |
| `Access denied` / 401 MCP после входа | Числовой `GITHUB_ALLOWED_USER_ID`, используемый GitHub-аккаунт |
| OAuth callback error | Совпадение домена, MCP_PUBLIC_URL и callback URL GitHub App |
| Список пуст | Пользователя JIRA_USERNAME и resolution в workflow |
| healthz OK, Jira не работает | Проверить API с MCP-хоста; healthz не обращается к Jira |

Проверка Jira с сервера (пароль запрашивается интерактивно):

```bash
curl -u 'YOUR_JIRA_LOGIN' 'https://jira.example.com/jira/rest/api/2/myself'
```

## Проверки проекта

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Автотесты проверяют GET и контекст `/jira`, пагинацию, запрет произвольных endpoints,
ошибки/редиректы, допуск по GitHub ID, отказ инструментов без токена и OAuth discovery/HTTP 401.
Проверено локально: 14 тестов. Docker-сборка, выпуск реального сертификата, реальный OAuth-вход
в ChatGPT и запросы к вашей Jira в этой среде не выполнялись.

## Источники

- Jira REST 8.5.1: https://docs.atlassian.com/software/jira/docs/api/REST/8.5.1/
- FastMCP GitHub OAuth: https://gofastmcp.com/integrations/github
- FastMCP OAuth Proxy: https://gofastmcp.com/servers/auth/oauth-proxy
- Подключение MCP к ChatGPT: https://developers.openai.com/api/docs/guides/custom-mcp-server
