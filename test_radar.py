from __future__ import annotations

import unittest

import indexador_lotes as indexador


class RadarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evento = {
            "nome": "Leilao de teste",
            "data": "2026-12-31",
            "data_original": "31/12/2026",
            "hora_marcador": "10:00",
            "uf": "MG",
            "endereco_ou_localizacao": "Taiobeiras - MG",
        }

    def test_extrai_lote_de_texto(self) -> None:
        rows = indexador.lot_rows_from_text(
            self.evento,
            "https://exemplo.com/leilao/1",
            "https://exemplo.com/edital.pdf",
            "\nLOTE 01 - Escavadeira hidraulica, lance minimo R$ 100.000,00\n",
            "pdf_ok",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lote"], "01")
        self.assertIn("Escavadeira", rows[0]["titulo"])

    def test_ignora_clausula_juridica(self) -> None:
        rows = indexador.lot_rows_from_text(
            self.evento,
            "https://exemplo.com/leilao/1",
            "https://exemplo.com/edital.pdf",
            "\nLOTE 9.19 - O pagamento seguira o item 12.2 deste edital.\n",
            "pdf_ok",
        )
        self.assertEqual(rows, [])

    def test_prioriza_site_sobre_google_drive(self) -> None:
        evento = {
            **self.evento,
            "site_leiloeiro": "https://exemplo.com/leilao/1",
            "link": "https://drive.google.com/file/d/abc/view",
        }
        self.assertEqual(indexador.event_urls(evento)[0], "https://exemplo.com/leilao/1")

    def test_rejeita_link_social(self) -> None:
        self.assertFalse(indexador.looks_like_lot("WhatsApp", "https://api.whatsapp.com/send?text=lote"))


if __name__ == "__main__":
    unittest.main()
