# MAISON API — инструкция для frontend и Flutter

База локально: `http://127.0.0.1:8000/api/v1/`. Все маршруты заканчиваются `/`. Swagger: `/api/docs/`; схема OpenAPI: `/api/schema/` и файл `openapi.yaml`.

JSON передавайте с `Content-Type: application/json`. Аватар — `multipart/form-data`. Для защищённых запросов:

```http
Authorization: Bearer <access>
```

В Swagger нажмите **Authorize** и вставьте сам access-токен без слова Bearer. API использует JWT; cookie-сессии админки не заменяют токен API. `access` действует 30 минут, `refresh` — 7 дней. При истечении access получите новый через refresh; при отказе refresh покажите вход. Endpoint выхода отсутствует: клиент удаляет токены; выданный токен остаётся действующим до истечения срока.

Все списки имеют формат:

```json
{"count": 15, "next": "http://127.0.0.1:8000/api/v1/menu/?page=2", "previous": null, "results": []}
```

По умолчанию 12 записей, следующая страница `?page=2`. Корзина — один объект с массивом `items`, поэтому не пагинируется. Цены — строки с двумя знаками, валюта демонстрационного меню — KGS (сом). Итог рассчитывает сервер. Дата брони `YYYY-MM-DD`, время `HH:MM` / `HH:MM:SS` по **Asia/Bishkek**. `created_at` — ISO 8601 с часовым поясом.

## Авторизация и профиль

| Метод | Путь | Доступ |
|---|---|---|
| POST | `auth/register/` | Все |
| POST | `auth/login/` | Все |
| POST | `auth/token/refresh/` | Все |
| GET, PATCH | `profile/` | Пользователь |

Регистрация:

```json
{"username":"daniel","email":"daniel@example.com","password":"MyStrongPass!2026","first_name":"Даниел","last_name":"Аскербеков","phone":"+996700123456"}
```

Уникальны `username`, email без учёта регистра и телефон. Формат телефона: `+` и 8–15 цифр, без пробелов. Пароль минимум 8 символов; слишком распространённый, полностью цифровой или похожий на данные пользователя отклоняется. Ответ 201 — профиль; токены получают отдельным входом.

Вход использует **username**, не email:

```json
{"username":"daniel","password":"MyStrongPass!2026"}
```

Ответ:

```json
{"refresh":"...","access":"..."}
```

Обновление: `POST auth/token/refresh/` с `{"refresh":"..."}`. Ответ `{"access":"..."}`.

В профиле редактируются `email`, `first_name`, `last_name`, `phone`, `avatar`. Имя входа не меняется. Для аватара отправляйте `FormData` с полем `avatar`, максимум 5 МБ; браузер сам установит Content-Type с boundary. Ответ содержит URL изображения или `null`; у администратора без созданного UserProfile поля телефона/аватара могут отсутствовать до заполнения телефона.

## Меню

| Метод | Путь | Описание |
|---|---|---|
| GET | `categories/` | Активные категории |
| GET | `menu/` | Блюда активных категорий |
| GET | `menu/{slug}/` | Одно блюдо по slug |
| GET | `menu/popular/` | Популярные доступные блюда |

Пример: `menu/?category=1&is_vegetarian=true&search=салат&ordering=price&page=1`.
Поддерживаются `category` (ID), `is_vegetarian`, `is_available`, `is_popular`, `search`, `ordering=price` / `-price` / `name` / `id`. Обычный список включает временно недоступные блюда: отображайте их с отключённой кнопкой заказа либо фильтруйте `is_available=true`. Неактивные категории скрыты вместе с блюдами.

```json
{"id":1,"category":1,"category_name":"Салаты","name":"Греческий салат","slug":"greek-salad","description":"...","price":"350.00","image":null,"is_vegetarian":true,"is_popular":true,"is_available":true}
```

У изображений может быть `null` — показывайте заглушку. В HTTP-ответе загруженные изображения имеют абсолютный URL. Блюдо в корзину передаётся по числовому `id`, а страница блюда открывается по `slug`.

## Бронирование

| Метод | Путь | Доступ |
|---|---|---|
| GET | `reservations/availability/?date=2027-01-15&time=18:00&guests=2` | Все |
| POST | `reservations/` | Все |
| GET | `reservations/` | Свои брони пользователя |
| PATCH | `reservations/{id}/cancel/` | Владелец брони |

Всегда выбирайте будущую дату: дата примера не является фиксированной тестовой датой. Availability возвращает пагинированные столы `{"id":1,"number":1,"seats":2}`. При бронировании сервер повторно проверит доступность — список свободных столов не гарантирует удержание места.

```json
{"table":1,"name":"Даниел","phone":"+996700123456","date":"2027-01-15","time":"18:00","guests_count":2,"comment":"Место у окна, если возможно"}
```

Ответ 201 включает `id`, `table_number`, `status: "pending"`, `created_at` и поля запроса. При входе бронь привязывается к текущему пользователю. У гостя она не появляется в личном кабинете после регистрации: отмена через сотрудников ресторана. Передавайте имя и телефон и для авторизованного клиента.

Бронь длится ровно 2 часа; разрешено соседство 14:00–16:00 и 16:00–18:00. Пересечение с `pending` или `confirmed` запрещено. Отменённая бронь стол не занимает. Вся бронь должна помещаться в рабочий день; при графике 10:00–22:00 последняя запись — 20:00.

Отмена: `PATCH reservations/12/cancel/` с пустым телом `{}`. Разрешено `pending → cancelled`, `confirmed → cancelled`. Повторная отмена возвращает уже отменённую запись. Чужая бронь — 404, гость не может запрашивать список броней.

## Корзина и заказ

| Метод | Путь | Описание |
|---|---|---|
| GET | `cart/` | Своя корзина |
| POST | `cart/items/` | Добавить блюдо |
| PATCH | `cart/items/{id}/` | Изменить количество |
| DELETE | `cart/items/{id}/` | Удалить позицию |
| POST | `orders/` | Оформить из корзины |
| GET | `orders/` | История своих заказов |
| GET | `orders/{id}/` | Свой заказ |

Все маршруты требуют токен. Добавление: `{"item":1,"quantity":2}`. Повторное добавление того же блюда **увеличивает** количество. Ограничение — 1–99 порций на блюдо. Изменение: `{"quantity":3}` **заменяет** количество. В URL используется ID позиции корзины, не ID блюда. `DELETE` возвращает 204 без JSON.

Пример корзины:

```json
{"id":1,"items":[{"id":7,"item":1,"item_details":{"id":1,"name":"Греческий салат","price":"350.00"},"quantity":2,"subtotal":"700.00"}],"total_price":"700.00"}
```

`item_details` содержит полную карточку меню; в примере сокращено. Оформление доставки:

```json
{"order_type":"delivery","delivery_address":"Бишкек, улица и дом, квартира","phone":"+996700123456","comment":"Позвонить при прибытии"}
```

Для самовывоза: `{"order_type":"pickup","phone":"+996700123456"}`. Позиции, цену и статус передавать не нужно: сервер берёт свою корзину, проверяет доступность и рассчитывает итог. Стоимость доставки в ТЗ не задана: `total_price` — сумма блюд без отдельного сбора.

Ответ 201 — заказ:

```json
{"id":5,"order_type":"pickup","status":"new","delivery_address":"","phone":"+996700123456","comment":"","total_price":"700.00","items":[{"id":8,"item":1,"item_name":"Греческий салат","quantity":2,"price":"350.00"}],"created_at":"2026-10-30T18:00:00+06:00"}
```

После успеха корзина очищена. При пустой корзине, недоступном блюде или отсутствии адреса доставки — 400, корзина сохраняется. Цена заказа не меняется после изменения цены в меню. Клиент не может менять статус заказа. На кнопке оформления блокируйте повторное нажатие до ответа; специальный `Idempotency-Key` не реализован. После сетевой ошибки проверьте историю заказов перед повтором.

## Отзывы и контакты

| Метод | Путь | Описание |
|---|---|---|
| GET | `reviews/` | Только одобренные отзывы, публично |
| POST | `reviews/` | Отзыв авторизованного пользователя |
| GET | `restaurant-info/` | Контакты, график и «О нас», публично |
| POST | `contact/` | Контактная форма, публично |

Отзыв: `{"rating":5,"text":"Всё понравилось"}`. Ответ 201, `is_approved=false`; показывайте «Отзыв отправлен на модерацию», он пока отсутствует в общем списке. Оценка — целое число 1–5.

Обращение: `{"name":"Даниел","email":"daniel@example.com","phone":"+996700123456","message":"Хочу уточнить меню"}`. Телефон необязателен. Ответ 201 означает сохранение обращения для сотрудников; рассылка писем не подключена.

`restaurant-info/` возвращает `name`, `address`, `phone`, `email`, `instagram`, `facebook`, `working_hours`, `about`. График: ключи `"0"`–`"6"` от понедельника до воскресенья, значение `{"open":"10:00","close":"22:00"}` или `null` для выходного. Ночные смены через полночь не поддерживаются.

## Административный API

Все пути ниже тоже начинаются с `/api/v1/`. Нужен JWT пользователя с `is_staff=true`. Django Admin доступен отдельно по `/admin/` с обычным входом username/password.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `admin-api/reservations/` и `admin-api/reservations/{id}/` | Все брони |
| PATCH | `admin-api/reservations/{id}/` | `{"status":"confirmed"}` |
| GET | `admin-api/orders/` и `admin-api/orders/{id}/` | Все заказы |
| PATCH | `admin-api/orders/{id}/` | `{"status":"cooking"}` |
| GET | `admin-api/reviews/` и `admin-api/reviews/{id}/` | Все отзывы, включая ожидающие |
| POST | `admin-api/reviews/{id}/approve/` | Одобрение, пустое тело |
| GET | `admin-api/contact-messages/` и `admin-api/contact-messages/{id}/` | Обращения |
| PATCH | `admin-api/contact-messages/{id}/` | `{"is_processed":true}` |

Фильтры: брони — `status`, `date`, `table`; заказы — `status`, `order_type`; отзывы — `is_approved`; обращения — `is_processed`.

Статусы брони: `pending → confirmed → cancelled`, также `pending → cancelled`. Из cancelled возврат запрещён.

Статусы заказа: `new → confirmed → cooking → delivered`. Отмена разрешена из new и confirmed. delivered/cancelled — конечные. Для самовывоза delivered означает «выдан». Повторная установка текущего статуса допустима. В Django Admin изменения статусов выполняются действиями, поля исходных броней и заказов доступны для чтения, чтобы обход формы не нарушал бизнес-правила. Меню, столы и контакты редактируются через Django Admin.

## Ошибки и ограничения

| Код | Значение |
|---|---|
| 200 | Получение / изменение |
| 201 | Создано |
| 204 | Удалено, пустое тело |
| 400 | Неверные данные или конфликт брони / заказа |
| 401 | Нужна авторизация либо неверный / истёкший токен |
| 403 | Недостаточно прав |
| 404 | Запись не найдена или принадлежит другому пользователю |
| 405 | Метод не поддерживается |
| 429 | Слишком много запросов; учитывайте Retry-After |

Ошибки DRF: `{"phone":["...ошибка..."]}`, `{"non_field_errors":["..."]}` либо `{"detail":"..."}`. Показывайте ошибки рядом с полями и общий текст для detail. Для брони занятый стол возвращает 400 с ключом `table`.

Ограничения: вход/регистрация/refresh — 10 запросов в минуту на IP или пользователя, создание брони — 10 в час, контактная форма — 5 в час. Общий лимит остальных публичных запросов — 120 в час, авторизованных — 1000 в час. В локальной разработке перезапуск очищает in-memory cache. Для нескольких рабочих процессов настройте общий cache.

## Минимальный пример JavaScript

```javascript
const baseUrl = 'http://127.0.0.1:8000/api/v1/';

async function request(path, { token, ...options } = {}) {
  const response = await fetch(baseUrl + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw { status: response.status, data };
  return data;
}

const tokens = await request('auth/login/', {
  method: 'POST',
  body: JSON.stringify({ username: 'demo_admin', password: 'MaisonDemo!2026' }),
});
const menu = await request('menu/?is_available=true');
await request('cart/items/', {
  method: 'POST', token: tokens.access,
  body: JSON.stringify({ item: menu.results[0].id, quantity: 1 }),
});
const cart = await request('cart/', { token: tokens.access });
console.log(cart);
```

Демо-вход предназначен только для локальной проверки. Создайте обычного пользователя для интерфейса клиента. В Flutter передавайте тот же Bearer header и обрабатывайте те же JSON-ответы.
