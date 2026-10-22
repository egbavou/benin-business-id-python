# Plan d'implémentation : `benin-business-id` pour Python

**Conception** : `docs/design/benin-business-id-python.md` (P1 à P17).
**Exécutant** : Claude (P13). Chaque étape se termine par ses tests verts. À la fin, Claude lance la vérification complète puis présente le diff.
**Interdits** : aucun commit, aucun push, aucune création de dépôt GitHub, aucune publication PyPI sans l'accord explicite de l'utilisateur.

Tout le contenu du dépôt est en anglais, sauf `docs/` et le catalogue Django français.

---

## Étape 0 : socle du projet

**Fichiers :**
- `pyproject.toml` :
  - nom, version `0.1.0`, `requires-python >=3.11`, `license = "MIT"` ;
  - backend `hatchling>=1.27` ;
  - extras `httpx`, `django`, `pydantic` ;
  - groupes `test` (pytest, Babel), `typing` (mypy, django-stubs), `lint` (ruff) ;
  - configuration de ruff, de mypy (`strict`, `src` et `tests`) et de pytest (marqueurs `live` et `parity`, `--strict-markers`, exclusion par défaut) ;
  - contenu du sdist (§5 de la conception).
- `LICENSE` (MIT, « Copyright (c) 2026 Egbavou »).
- `.gitignore`, qui exclut `uv.lock`.
- `src/benin_business_id/__init__.py` et `py.typed`.
- Tests asynchrones dans `asyncio.run()`, sans greffon pytest.

**Puis :** `uv sync --all-extras --all-groups`. C'est Claude qui fait l'installation, car il a accès au réseau.

**Contrôle :** `uv run pytest` part, `uv run mypy` et `uv run ruff check` passent.

## Étape 1 : énumérations, erreurs, nettoyage, horloge

**Fichiers :**
- `_enums.py` : les cinq enums (§6.1) ;
- `_errors.py` : `InvalidIdentifierError` (propriété `reason`, `__reduce__`), `DirectoryError` ;
- `_cleanup.py` : `PCRE_SPACE`, expression de nettoyage, majuscules ASCII ;
- `_clock.py` : `current_year()`.

**Tests (`tests/core/`) :**
- valeurs et ordre exacts des enums, comme le test PHP sur les six causes ;
- messages des erreurs et aller-retour `pickle` ;
- `TaxpayerType.from_digit` : `InvalidIdentifierError` pour -1, 7, 8, 9 et 10 ; `TypeError` pour `True` et `1.0` ;
- test exhaustif du nettoyage, de U+0000 à U+10FFFF (§13.1).

## Étape 2 : `Ifu` et `Rccm`

**Fichiers :** `_ifu.py`, `_rccm.py`, `tests/cases.py` (vecteurs portés d'`IdentifierCases.php`).

**Tests :**
- tous les cas valides et invalides du PHP, sauf les octets invalides `"\xFF"`, remplacés par `"\udcff"` (§12.2 de la conception) ;
- bornes d'année calculées depuis l'année courante ;
- pivot de siècle, en plus testé avec une année courante fixée (monkeypatch de `_clock.current_year`), par exemple 2089 et 2100 ;
- greffes actifs et anciens ;
- `TypeError` pour une entrée qui n'est pas un `str` (`int`, `bytes`, `None`, `list`), sur les trois points d'entrée ;
- sous-classe de `str` ;
- égalité, hachage, `repr`, `str`, `format()`, `pickle`, `copy`, `dataclasses.replace()` ;
- majuscules ASCII : `ı`, `ſ`, `ß` donnent `INVALID_CHARACTERS`.

## Étape 3 : compatibilité PHP (`_php.py`)

**Fonctions :**
- `trim` ;
- `float_to_string` ;
- `json_decode` (§9.4 de la conception) ;
- `env_value` (lecture `env()` de Laravel) ;
- `filter_bool` ;
- `is_numeric`.

**Tests :** un cas par ligne du tableau du §9.4 et par règle du §8, plus les exemples vérifiés sur PHP 8.5 :
- flottants `12.5`, `1`, `1.0E+20`, `1.0E-7`, `0.3`, `-0`, `INF`, `-INF` ;
- profondeur 511 acceptée, 512 refusée, y compris dans une valeur écrasée par une clé en double ;
- substitut isolé refusé, y compris dans une valeur écrasée ;
- clé commençant par U+0000 refusée ; clé vide et clé contenant U+0000 ailleurs acceptées ;
- `9223372036854775808` donne un flottant, `-9223372036854775808` un entier ;
- un entier de 5 000 chiffres donne `inf` ;
- `is_numeric` : `" 5 "`, `"\v2.5\f"`, `"5."`, `".5"`, `"1e999"` sont numériques ; `"1_0"`, `"inf"`, `"0x1A"`, U+00A0 suivi de `2`, `"\x002"` ne le sont pas ;
- `filter_var` : `"\vtrue\v"` donne vrai ; `"\ftrue\f"`, `"maybe"` et `2` donnent faux ; `1` et `1.0` donnent vrai ;
- `env()` : une valeur entre guillemets avec un saut de ligne garde ses guillemets.

## Étape 4 : configuration (`_settings.py`)

`ApiexSettings`, constantes `DEFAULT_*`, `from_env()`.

**Tests :**
- valeurs par défaut ;
- chaque règle `env()` : `true`, `(true)`, `FALSE`, `empty`, `null`, guillemets ;
- `filter_var` : `yes`, `on`, `1`, `" TRUE "`, `maybe` ;
- repli du délai sur 10 : `0`, `-1`, `abc`, `true`, vide ;
- repli des URL : vide, `null`, `true`.

## Étape 5 : APIEx sans réseau (`_apiex.py`)

**Fonctions pures :**
- `register_order(rccm)` ;
- `search_values(rccm, exact)` ;
- `filters(register, rccm, exact)` ;
- `request_url(base_url, register, rccm, exact)` ;
- `HEADERS` (`User-Agent` et `Accept`) ;
- `read_page(status, body, rccm)`, qui renvoie l'enregistrement trouvé ou `None` et lève `DirectoryError` ;
- `text`, `creation_date`, `former_number`, `details(record, register)`.

**Tests :** ceux de `RequestsTest.php`, à l'identique :
- filtres de `RB/COT/2005 B 40` ;
- `RB/COT/05 B 0040` ;
- pas d'année sur 4 chiffres après 2020 ;
- URL déjà munie d'une requête ;
- pas de `\/` dans le JSON ;
- encodage RFC 3986 de l'URL complète.

## Étape 6 : vérificateurs (`_checkers.py`, `_results.py`)

**Classes :** `IfuChecker`, `AsyncIfuChecker`, `RccmChecker`, `AsyncRccmChecker`, `IfuCheckResult`, `RccmCheckResult`.

**Requête :** un `httpx.Request` brut, envoyé par `client.send(request, follow_redirects=False)`, en synchrone comme en asynchrone (P14, P15).

**Tests :**
- dans `tests/core/` : `IfuChecker` et `AsyncIfuChecker`, et `RccmChecker` coupé sans httpx installé ;
- dans `tests/httpx_integration/` : tous les cas de `CheckersTest.php`, en synchrone puis en asynchrone, avec `httpx.MockTransport` :
  - les réponses du PHP deviennent des `httpx.Response` ;
  - les exceptions levées par le faux client deviennent des exceptions levées par le transport factice ;
  - l'URL refusée par la fabrique PHP devient une URL refusée par httpx ;
  - « `getBody()` lève après un 200 » devient une erreur injectée dans le décodeur, ce qui donne `SCHEMA` (P15) ;
  - une coupure pendant la lecture du corps donne `TRANSPORT`.

**Tests de requête :**
- en-têtes exacts sur le réseau : `host`, `user-agent`, `accept`, rien d'autre ;
- un client configuré avec `follow_redirects=True` reçoit quand même une réponse 301 sans la suivre, donc `HTTP_STATUS` ;
- un client configuré avec des `params` ne modifie pas l'URL ;
- le délai du client est appliqué à la requête brute.

**Tests propres à Python :**
- `TypeError` sur une entrée qui n'est pas un `str` ;
- `KeyboardInterrupt` et `asyncio.CancelledError` se propagent ;
- client injecté jamais fermé, client créé fermé par `close()` et `aclose()` ;
- `ValueError` si `client` et `timeout` sont passés ensemble, ou si `timeout` est ≤ 0 ;
- `ImportError` explicite sans httpx, uniquement si `enabled=True` ;
- `from_settings` ;
- `repr` et `pickle` d'un résultat ne contiennent aucune donnée personnelle sentinelle.

## Étape 7 : Pydantic (`pydantic.py`)

`PydanticIfu` et `PydanticRccm` : alias `Annotated` avec `PlainValidator`, `PlainSerializer` et `WithJsonSchema` (§10).

**Tests (`tests/pydantic_integration/`) :**
- valeurs valides : l'attribut est l'objet du cœur ; sérialisation normalisée en Python et en JSON ;
- valeurs invalides : type d'erreur `ifu_<raison>` ou `rccm_<raison>`, `ctx` et message ;
- valeurs qui ne sont pas des chaînes, dont un `Rccm` donné à `PydanticIfu` : `*_invalid_characters` ;
- objet déjà construit renvoyé tel quel ;
- mode strict ;
- schémas JSON de validation et de sérialisation ;
- alias facultatif (`PydanticIfu | None`).

Le plancher de Pydantic est déterminé ici par `uv sync --resolution lowest-direct` sur Python 3.11.

## Étape 8 : Django (`django/`)

**Fichiers :**
- `apps.py` ;
- `checkers.py` ;
- `validators.py` ;
- `forms.py` ;
- `locale/fr/LC_MESSAGES/django.po`, et le `.mo` compilé par `pybabel compile -D django`.

**Tests (`tests/django_integration/`) :** configuration minimale dans le `conftest.py` du dossier (`settings.configure`, puis `django.setup()`), sans pytest-django :
- validateurs de format :
  - chaque vecteur, avec `code` et message en anglais et en français ;
  - valeurs qui ne sont pas des chaînes ;
  - objet du bon type et du mauvais type ;
  - `deconstruct()`, puis reconstruction ;
  - égalité ;
- validateurs d'existence :
  - `NOT_FOUND` ;
  - `UNAVAILABLE` par défaut et en strict ;
  - `verification_disabled` ;
  - `FOUND` ;
  - `deconstruct()` et égalité, `fail_when_unavailable` compris ;
- champs de formulaire :
  - objet dans `cleaned_data` ;
  - valeur vide au sens du `trim` PHP (`" \t"`, `"\0"`), avec `required=True` puis `required=False` ;
  - chaîne d'espaces insécables ;
  - `"\x1c"` ;
  - `has_changed()`, champ désactivé, `prepare_value()`, `error_messages` ;
- vérificateurs partagés :
  - réglage `BENIN_BUSINESS_ID` avec repli sur l'environnement ;
  - `RCCM_CHECKER` injecté ;
  - `override_settings` qui renouvelle l'instance et ferme celle que le package avait créée ;
- traductions :
  - changement de langue après l'import ;
  - cohérence entre le `.mo` et le `.po` ;
  - chaque raison a un message dans chaque langue.

## Étape 9 : architecture, tests réels, parité

- **`tests/core/test_architecture.py`** : dans un sous-processus, `import benin_business_id` ne charge ni httpx, ni django, ni pydantic.
- **`tests/live/test_apiex.py`** : marqueur `live`, et saut sans `BENIN_BUSINESS_ID_LIVE=1`. Les 3 cas PHP, en synchrone et en asynchrone.
- **`tests/parity/oracle.php`** et **`tests/parity/test_parity.py`** : marqueur `parity`, saut si `php` ou le dossier PHP manque. Ils appliquent le protocole du §13.2 de la conception :
  - oracle PHP avec les opérations `ifu`, `rccm`, `check` et `settings` ;
  - corps APIEx transmis bruts en base64 ;
  - projection canonique ;
  - `checked_at` contrôlé par intervalle de chaque côté ;
  - `User-Agent` comparé modulo P1 ;
  - cas du §12.2 exclus à la génération.

## Étape 10 : CI et README

- **`.github/workflows/ci.yml`** : jobs `core`, `httpx`, `django`, `pydantic`, `quality` et `lowest` (§13.4 de la conception).
- **`README.md`** (anglais), sur le modèle du README PHP et du port France :
  - installation, extras, validation, vérification sync et async ;
  - tableau des causes, `failure` ;
  - mise en garde sur l'APIEx (source non documentée, `NOT_FOUND` n'est pas une preuve) ;
  - configuration, Django, Pydantic, développement ;
  - délai httpx par opération ;
  - limites et écarts connus.

## Vérification finale (Claude)

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
uv run pytest -m parity
uv build
```

S'y ajoutent :
- une passe cœur seul : environnement sans extras, groupe `test`, `pytest tests/core` ;
- une passe des versions minimales sur Python 3.11 ;
- le contrôle du wheel construit depuis le sdist (`py.typed`, `.po`, `.mo`).

Les tests réels (`-m live`) ne sont lancés qu'avec l'accord de l'utilisateur, puisqu'ils interrogent l'APIEx.

Ensuite : présentation des fichiers créés et des résultats. Pas de commit.
