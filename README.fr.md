[Deutsch](README.md) | [English](README.en.md) | Français

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![Licence](https://img.shields.io/badge/Licence-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction repère les données personnelles dans les documents de Nextcloud et les caviarde. La détection et le caviardage fonctionnent localement sur votre propre serveur, pour des textes en allemand, en anglais et en français.

**Statut :** en développement, pas encore dans l'App Store.

## Ce que fait PII Redaction

- Détecte noms, adresses, numéros de téléphone, adresses e-mail, IBAN et données similaires
- Caviardage réel : le texte est supprimé, pas seulement masqué
- Aperçu pour vérifier avant le caviardage, l'original est conservé
- Fonctionne entièrement dans votre propre instance, aucune télémétrie
- Ne modifie jamais vos fichiers

## Prérequis

- Nextcloud 33 à 35 avec AppAPI et un démon de déploiement configuré (HaRP recommandé)
- CPU : amd64 ou arm64

## Installation

Installer PII Redaction depuis la section External Apps de l'App Store. Les
réglages se trouvent ensuite dans Paramètres d'administration, Paramètres
supplémentaires.

## Architecture

PII Redaction est une External App : un conteneur Python (FastAPI) qu'AppAPI
démarre via le démon de déploiement et ne joint que par AppAPI/HaRP. Chaque
requête vers le conteneur porte la signature d'AppAPI ; sans elle, la réponse
est 401.

## Confidentialité

Tout fonctionne localement dans le conteneur, rien ne quitte votre serveur.
L'application n'enregistre que ses réglages et écrit la version caviardée dans un nouveau fichier ; aucun document ne quitte le serveur.

## Licence

AGPL-3.0-or-later. Voir [LICENSE](LICENSE).
