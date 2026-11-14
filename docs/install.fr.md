[Deutsch](install.md) | [English](install.en.md) | Français

# Installer PII Redaction

PII Redaction se compose de deux applications. Les deux sont nécessaires et doivent porter la même version :

- `pii_redaction_backend` : External App (conteneur Python), convertit DOCX et ODT en PDF, produit l'image de page et le PDF provisoire
- `pii_redaction` : application PHP, apporte l'action de fichier, la page de vérification, le contrôle des droits, les notifications, le dépôt de la copie et la section d'état

État 0.1.0 : la page de vérification montre un aperçu sans détection, la copie est provisoire. Les données personnelles ne sont encore ni recherchées ni caviardées.

## Ordre

1. Activer AppAPI et configurer le démon de déploiement HaRP.
2. Installer l'External App « PII Redaction Backend » (`pii_redaction_backend`) et attendre qu'elle soit activée.
3. Installer et activer l'application « PII Redaction » (`pii_redaction`) dans la même version.
4. Laisser l'application Notifications activée, sinon aucune notification n'apparaît.
5. Dans Paramètres d'administration, Paramètres de base, régler les tâches de fond sur Cron (voir la section Tâches de fond).
6. Vérifier l'état dans Paramètres d'administration, PII Redaction : attendu est « Les deux applications sont connectées. »

## Même version (lockstep)

- Les deux applications portent toujours le même numéro de version. Après une mise à jour, mettre les deux applications à la même version.
- Si les versions ne diffèrent que par le dernier chiffre (par exemple 0.1.0 et 0.1.1), les analyses continuent.
- Si elles diffèrent par le premier ou le deuxième chiffre, aucune nouvelle analyse ne démarre et aucune copie ne peut être créée sur la page de vérification tant que les deux applications ne correspondent pas.
- Tant que l'application PHP est désactivée, le backend ne prend aucune tâche.

## États de la section d'état

La section d'état dans Paramètres d'administration, PII Redaction montre exactement un état, en dessous les versions des deux applications, l'heure de la dernière vérification et le bouton « Vérifier à nouveau » :

- **Succès, « Les deux applications sont connectées. »** Tout va bien, rien à faire.
- **Information, « Petite différence de version. »** Les versions diffèrent par le dernier chiffre. Les analyses fonctionnent ; aligner les deux applications à la prochaine mise à jour.
- **Erreur, « Les versions ne correspondent pas. »** Les versions diffèrent par le premier ou le deuxième chiffre. Mettre les deux applications à la même version.
- **Erreur, « Le backend n'est pas installé. »** `pii_redaction_backend` manque. Installer l'External App.
- **Erreur, « Le backend est désactivé. »** `pii_redaction_backend` est installé mais arrêté. L'activer dans Applications.
- **Erreur, « Le backend ne répond pas. »** Le conteneur ne tourne pas ou HaRP n'est pas joignable. Vérifier dans Applications et dans les paramètres d'AppAPI.
- **Erreur, « AppAPI n'est pas activé. »** Sans AppAPI, le backend ne fonctionne pas. Activer AppAPI et configurer HaRP.
- **Avertissement, « L'état n'a pas pu être vérifié de nouveau. »** « Vérifier à nouveau » n'a pas abouti ; l'affichage reste celui du chargement de la page. Vérifier plus tard.

À chaque erreur, le lien « Ouvrir Applications » mène à la gestion des applications. Tant qu'une erreur persiste, aucune analyse ne démarre et aucune copie ne peut être créée sur la page de vérification. Au démarrage, les utilisateurs voient « PII Redaction n'est pas prêt. Prévenez l'administration. »

## Tâches de fond

Une tâche de fond de Nextcloud place la copie à côté de l'original. En mode AJAX, elle ne s'exécute que lorsque quelqu'un ouvre une page ; la copie apparaît alors en retard. Le mode Cron est recommandé.

## Remarques

- Sont analysés les fichiers PDF, DOCX et ODT, toujours un seul fichier. L'action de fichier n'apparaît pas pour une sélection multiple, dans la corbeille, sur les pages de partage public ni pour les dossiers.
- Une seule tâche s'exécute à la fois. Les autres attendent dans la file.
- **Fichier modifié :** au démarrage, l'application retient l'état du fichier (etag). S'il change ensuite, la vérification est périmée : la page de vérification indique « Le fichier a été modifié », le fichier doit être analysé de nouveau. Les stockages externes peuvent attribuer un nouvel etag sans modification du contenu, par exemple lors d'une nouvelle lecture. L'application demande alors aussi une nouvelle analyse. C'est voulu : mieux vaut une analyse de plus qu'une copie faite à partir d'un autre état.
- **Téléchargement bloqué :** si un partage n'autorise pas le téléchargement, aucune analyse ne démarre, sans exception. Si le blocage est posé plus tard, la page de vérification ne montre plus d'image de page et aucune copie n'est créée.
- **Original supprimé :** l'analyse s'arrête, aucune notification ne suit.
- La copie est toujours un PDF et n'écrase jamais un fichier existant. Si le nom est pris, ` (2)` est ajouté.
