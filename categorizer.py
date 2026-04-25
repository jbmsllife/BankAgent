import os
import json
import anthropic

CATEGORIES = [
    "Alimentation/Courses",
    "Restaurant/Café",
    "Transport",
    "Logement/Loyer",
    "Santé",
    "Loisirs/Entertainment",
    "Shopping/Vêtements",
    "Services/Abonnements",
    "Voyages",
    "Salaire/Revenus",
    "Virements",
    "Banque/Frais",
    "Impôts/Taxes",
    "Autre",
]

_CATEGORIES_STR = "\n".join(f"- {c}" for c in CATEGORIES)

SYSTEM_PROMPT = f"""Tu es un assistant expert en finances personnelles. Tu catégorises des transactions bancaires françaises.

Catégories disponibles :
{_CATEGORIES_STR}

Règles :
- Supermarché / épicerie / drive → Alimentation/Courses
- McDonald's, restaurants, cafés → Restaurant/Café
- SNCF, Uber, carburant, parking → Transport
- Loyer, EDF, internet, assurance habitation → Logement/Loyer
- Pharmacie, médecin, mutuelle → Santé
- Netflix, Spotify, cinéma, jeux → Loisirs/Entertainment
- Amazon, Zara, H&M → Shopping/Vêtements
- Abonnements téléphone, SaaS → Services/Abonnements
- Booking, Airbnb, compagnies aériennes → Voyages
- Salaire, remboursement → Salaire/Revenus
- Virement entre comptes perso → Virements
- Frais bancaires, agios → Banque/Frais
- Impôts, taxes → Impôts/Taxes
- Tout le reste → Autre

Réponds UNIQUEMENT avec un objet JSON :
{{"categories": ["cat1", "cat2", ...]}}

Le tableau doit contenir EXACTEMENT autant d'éléments que de transactions fournies.
"""


class Categorizer:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY manquant. Créez un fichier .env et ajoutez votre clé API."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

    def categorize_batch(self, transactions: list[dict], batch_size: int = 40) -> list[dict]:
        result = []
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i : i + batch_size]
            result.extend(self._call_claude(batch))
        return result

    def _call_claude(self, transactions: list[dict]) -> list[dict]:
        txn_text = "\n".join(
            f"{i+1}. {t['date']} | {t['description']} | {t['amount']:+.2f}€"
            for i, t in enumerate(transactions)
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},  # cache le prompt système
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"Catégorise ces {len(transactions)} transactions :\n\n{txn_text}",
                    }
                ],
            )

            text = response.content[0].text.strip()
            # Nettoie les blocs de code éventuels
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            categories = data.get("categories", [])

            for i, t in enumerate(transactions):
                cat = categories[i] if i < len(categories) else "Autre"
                t["category"] = cat if cat in CATEGORIES else "Autre"

        except Exception as e:
            print(f"Erreur Claude ({self.model}): {e}")
            for t in transactions:
                t["category"] = "Autre"

        return transactions
