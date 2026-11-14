[Deutsch](README.md) | [English](README.en.md) | Français

# PII Redaction

[![Python gates](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/python.yml)
[![Security scans](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml/badge.svg)](https://github.com/street1983nk/nextcloud-pii-redaction/actions/workflows/security.yml)
[![Nextcloud App Store](https://img.shields.io/badge/App_Store-pii__redaction-0082c9)](https://apps.nextcloud.com/apps/pii_redaction)
[![Licence](https://img.shields.io/badge/Licence-AGPL--3.0--or--later-blue)](LICENSE)

PII Redaction doit repérer les données personnelles dans les fichiers PDF, DOCX et ODT de Nextcloud et les caviarder après une vérification humaine. Tout fonctionne localement sur votre propre serveur.

**Statut :** en développement, pas encore dans l'App Store. État 0.1.0 : une base de deux applications avec une page de vérification et une copie provisoire. Il n'y a pas encore de détection des données personnelles ni de caviardage.

## Ce que fait PII Redaction 0.1.0

- Action de fichier « Caviarder / pseudonymiser » dans l'application Fichiers, pour un seul fichier PDF, DOCX ou ODT
- Une tâche à la fois ; les autres attendent dans une file, le message de démarrage indique le nombre de tâches avant
- Le backend convertit DOCX et ODT en PDF avec LibreOffice
- Page de vérification avec la progression et la page 1 en image, signalée comme « Aperçu sans détection »
- « Créer une copie provisoire » place à côté de l'original un PDF d'une page qui ne contient rien de l'original, par exemple `Bescheid_caviardé.pdf` (allemand `_geschwärzt`, anglais `_redacted`) ; un nom déjà pris reçoit ` (2)`
- L'original reste inchangé
- Notifications quand une vérification est prête, qu'une analyse échoue, que le fichier a été modifié ou que la copie a été créée
- Section d'état pour les administrateurs avec l'état des deux applications
- Textes en allemand, en anglais et en français
- Prévu, pas encore construit : détection des données personnelles, caviardage et pseudonymisation, contrôle de la copie contre les restes

## Deux applications, toutes deux nécessaires

| Application | ID | Rôle |
|---|---|---|
| PII Redaction | `pii_redaction` | Application PHP : action de fichier, page de vérification, contrôle des droits, notifications, dépôt de la copie, section d'état |
| PII Redaction Backend | `pii_redaction_backend` | External App (conteneur Python) : conversion en PDF, image de page, PDF provisoire |

Les deux applications doivent être installées et porter la même version. Si les versions ne diffèrent que par le dernier chiffre, les analyses continuent ; sinon aucune nouvelle analyse ne démarre tant que les deux applications ne correspondent pas.

## Prérequis

- Nextcloud 33 à 35, PHP 8.2 ou plus récent
- AppAPI avec le démon de déploiement HaRP
- CPU : amd64 ou arm64, pas de GPU nécessaire
- Tâches de fond en mode Cron recommandé : une tâche de fond place la copie
- Application Notifications pour les notifications

## Installation

En bref : AppAPI avec HaRP, puis l'External App `pii_redaction_backend`, puis l'application PHP `pii_redaction` dans la même version. L'état des deux applications apparaît ensuite dans Paramètres d'administration, PII Redaction. Toutes les étapes et le sens de chaque message de la section d'état : [docs/install.fr.md](docs/install.fr.md).

## Architecture

L'application PHP vérifie les droits de l'utilisateur à chaque étape et transmet le fichier au backend par une interface, via l'ID du fichier. Le backend est une External App : un conteneur Python (FastAPI) qu'AppAPI démarre via HaRP. Le conteneur n'a aucune route pour le navigateur ; chaque requête vers lui porte la signature d'AppAPI, sans elle la réponse est 401. L'application PHP écrit la copie au nom de l'utilisateur qui a lancé l'analyse ; le conteneur n'a aucun accès en écriture aux fichiers des utilisateurs.

## Confidentialité

- Tout fonctionne localement sur votre propre serveur, aucun contenu ne quitte le serveur, aucune télémétrie
- Les notifications ne nomment aucun fichier, elles renvoient seulement à la page de vérification
- Les tables de l'application dans la base de données de Nextcloud n'enregistrent aucun nom de fichier, seulement l'ID du fichier, l'utilisateur et l'état de la tâche
- Les données intermédiaires (fichier, PDF, image de page) restent dans le volume de données du conteneur ; le backend les supprime dès que la copie est créée ou que la tâche se termine
- La version 0.1.0 ne supprime pas encore les vérifications ouvertes après un délai

## Licence

AGPL-3.0-or-later. Voir [LICENSE](LICENSE).

Composants tiers dans l'image du backend :

- PyMuPDF (AGPL-3.0) produit l'image de page et écrit le PDF provisoire
- LibreOffice (paquet Debian `libreoffice-writer-nogui`) convertit DOCX et ODT en PDF, avec les paquets de polices `fonts-liberation2`, `fonts-dejavu-core`, `fonts-crosextra-carlito` et `fonts-crosextra-caladea` ; les textes de licence des paquets Debian se trouvent dans l'image sous `/usr/share/doc/<paquet>/copyright`

Icônes de l'application PHP : Material Design Icons de Pictogrammers, Apache-2.0.
