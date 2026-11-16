# Comparaison avec les directives de sécurité Nextcloud (PII Redaction)

Annexe au dossier de sécurité. État au 16.11.2026, vérifié par rapport aux
directives de sécurité du manuel développeur Nextcloud 35
(developer_manual/prologue/security.html) et aux règles de l'app store
(app_publishing_maintenance/publishing.html). Méthode : un balayage du code
sur php/ et backend/src le 16.11.2026 (shell_exec, proc_open, passthru,
eval, SQL brut, print_unescaped, innerHTML, os.system : 0 occurrence) plus
l'audit de sécurité de la phase 1 (01-SECURITY.md, 103 menaces, 0 ouverte).

## Directives développeur

| Règle | État | Preuve |
|---|---|---|
| Injection SQL : uniquement des requêtes préparées | respecté | IQueryBuilder dans tous les mappers ; aucun SQL brut dans le balayage ; stockage du backend avec des requêtes sqlite paramétrées |
| XSS : assainir les templates et le DOM | respecté | Page de vérification en application Vue avec échappement des templates, CSP sans scripts en ligne ; aucun innerHTML avec des données utilisateur (balayage) |
| Clickjacking | respecté | Les en-têtes par défaut restent intacts |
| Exécution de code / inclusion de fichiers | respecté | Balayage 0 occurrence ; documents uniquement dans le volume ExApp, jamais dans le webroot |
| Traversée de répertoires : API de fichiers | respecté | Accès aux fichiers par IRootFolder après contrôle des droits ; PHP écrit le résultat en tant qu'utilisateur par l'API de fichiers, le conteneur n'a aucun accès en écriture aux fichiers des utilisateurs |
| Injection shell | respecté | PHP n'appelle aucun shell (balayage) ; LibreOffice/Tesseract en processus enfants avec liste d'arguments, sans shell (plans de la phase 2 : prison avec environnement vidé) |
| Contournement d'authentification / élévation de privilèges | respecté | L'action sur fichier, la page de vérification et le journal contrôlent les droits en PHP ; audit de la phase 1 vérifié |
| Exposition de données sensibles | respecté | Journalisation durcie (aucun texte d'exception, garde-fou LOG_CONTEXT_KEYS avec autotest, ni chemin ni nom dans le journal) ; les voies de lecture de secrets depuis le conteneur font l'objet des plans de la phase 2 (prctl DUMPABLE=0, Landlock, frpc 0711) |
| CSRF | respecté | Standard du framework d'applications ; les POST portent le requesttoken |
| Redirections non validées | s. o. | Aucune redirection |
| CORS | s. o. | Aucune autorisation CORS |

## Règles de l'app store (extrait)

| Règle | État | Preuve |
|---|---|---|
| AGPL-3.0-or-later | respecté | LICENSE, info.xml ; l'AGPL de PyMuPDF est compatible ; examen de la licence LGPL-LR de fr_core_news_lg documenté (CLAUDE.md) |
| Pas de « Nextcloud » dans le nom | respecté | pii_redaction / pii_redaction_backend |
| Réaction rapide aux signalements de sécurité | respecté | SECURITY.md (signalement privé GitHub plus courriel, 7 jours) ; en pratique : garde-fou pip-audit sur main plus processus de correction des CVE |
| Installation, désinstallation et mises à niveau propres | respecté | Migrations avec tests, le gestionnaire enabled nettoie les anciens états (push 11) |
| Aucune donnée à des tiers, protection de la vie privée | respecté | Ni contenu de document, ni résultat, ni télémétrie ne quitte le serveur ; téléchargements de modèles avec un sha256 fixe ; la coupure des accès réseau des bibliothèques (tldextract/Presidio/GLiNER2) est un critère de la phase 2 avec une preuve --network-none sur l'image réelle |
| Moyen de contact | respecté | Issues GitHub, SECURITY.md |

## Au-delà des directives

- Audit des menaces par phase (01-SECURITY.md vérifié, 103 menaces) ; la phase 2 EST la phase de durcissement (bac à sable des processus enfants, contrôle préalable en fail-closed, corpus dans la CI)
- Épinglage des workflows, pip-audit sur le fichier de verrouillage, composer.lock imposé
- Fail-closed comme base : le refus est la voie sûre

## Points ouverts

- Cette comparaison sera complétée par les preuves du bac à sable après l'audit de sécurité de la phase 2 (02-SECURITY.md) (sonde seccomp/Landlock, mesure frpc 0711 A1, preuve réseau).
