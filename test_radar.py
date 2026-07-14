from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import indexador_lotes as indexador
import atualizar_radar_leiloes as atualizador


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

    def test_extrai_foto_do_json_do_lote(self) -> None:
        item = {"title": "Lote 12 - Escavadeira", "images": [{"url": "/fotos/lote-12.jpg"}]}
        self.assertEqual(
            indexador.image_from_dict(item, "https://leiloeiro.com/evento/1"),
            "https://leiloeiro.com/fotos/lote-12.jpg",
        )

    def test_extrai_foto_de_card_html(self) -> None:
        page = '<a href="/lote/7"><img data-src="/fotos/7.webp" alt="Lote 7 - Caminhão"></a>'
        event = {"nome": "Leilão teste", "data": "2099-01-01", "link": "https://leiloeiro.com/evento"}
        rows = indexador.extract_lots_from_page(
            event,
            event["link"],
            page,
            "https://leiloeiro.com/evento",
            "ok",
        )
        self.assertEqual(rows[0]["foto_lote"], "https://leiloeiro.com/fotos/7.webp")

    def test_rejeita_logo_como_foto_do_lote(self) -> None:
        self.assertEqual(indexador.valid_image_url("/assets/logo-site.png", "https://leiloeiro.com"), "")

    def test_extrai_foto_de_background_do_card(self) -> None:
        parser = indexador.LinkParser()
        parser.feed('<a href="/lote/9"><div style="background-image:url(/fotos/9.jpg)">Lote 9</div></a>')
        self.assertEqual(parser.link_images["/lote/9"], "/fotos/9.jpg")

    def test_lote_extraido_do_pdf_guarda_link_do_edital(self) -> None:
        evento = {**self.evento, "link_edital": "https://exemplo.com/edital.pdf"}
        rows = indexador.lot_rows_from_text(
            evento,
            "https://exemplo.com/leilao/1",
            "https://exemplo.com/edital.pdf",
            "\nLOTE 01 - Caminhao basculante, lance minimo R$ 90.000,00\n",
            "pdf_ok",
        )
        self.assertEqual(rows[0]["link_edital"], "https://exemplo.com/edital.pdf")

    def test_remove_evento_de_hoje_com_horario_passado(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        passado = {"data": "2026-07-14", "hora_marcador": "10:00"}
        futuro = {"data": "2026-07-14", "hora_marcador": "18:00"}
        self.assertFalse(atualizador.is_upcoming_event(passado, now))
        self.assertTrue(atualizador.is_upcoming_event(futuro, now))

    def test_remove_lote_de_data_passada(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertFalse(indexador.upcoming_lot({"data": "2026-07-13", "hora": "18:00"}, now))
        self.assertTrue(indexador.upcoming_lot({"data": "2026-07-15", "hora": "08:00"}, now))


if __name__ == "__main__":
    unittest.main()
