from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from datetime import datetime
from zoneinfo import ZoneInfo

import indexador_lotes as indexador
import atualizar_radar_leiloes as atualizador
import atualizar_licitacoes as licitacoes
import descobrir_licitacoes_openai as licitacoes_openai
import diagnostico_radar as diagnostico
import executar_atualizacao_radar as pipeline
import gerar_site_github as site
import sanitizar_conteudo_externo as sanitizer
from normalizar_texto import corrigir_dados, corrigir_texto, tem_codificacao_corrompida
from personalizar_site import apply_date_highlights


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

    def test_pdf_invalido_html_e_corrompido(self) -> None:
        self.assertEqual(indexador.pdf_text(b"<html>nao pdf</html>"), "")
        self.assertEqual(indexador.pdf_text(b"%PDF-corrompido"), "")

    def test_pdf_enorme_e_ignorado(self) -> None:
        with mock.patch.object(indexador, "PDF_MAX_BYTES", 8):
            self.assertEqual(indexador.pdf_text(b"%PDF-123456789"), "")

    def test_remove_evento_de_hoje_com_horario_passado(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        passado = {"data": "2026-07-14", "hora_marcador": "10:00"}
        futuro = {"data": "2026-07-14", "hora_marcador": "18:00"}
        self.assertFalse(atualizador.is_upcoming_event(passado, now))
        self.assertTrue(atualizador.is_upcoming_event(futuro, now))

    def test_data_iso_de_site_nao_vira_ano_seguinte(self) -> None:
        captured = atualizador.parse_datetime_from_text(
            'Leilão com startDate "2026-08-27 14:00:00"'
        )
        self.assertEqual(captured[:2], ("2026-08-27", "27/08/2026"))

    def test_recupera_evento_de_camada_csv_importada_incorretamente(self) -> None:
        data = {
            "TITULO;DATA;MARCADOR;DESCRIÇÃO;LOCALIZAÇÃO": (
                '[PREFEITURA] - Ônibus - Camutanga / PE;28/08/2026;04:00;'
                '"<a href=""https://exemplo.com/leilao/1"">Abrir</a>";'
                "Av. Presidente Getúlio Vargas"
            )
        }
        recovered = atualizador.embedded_semicolon_event(data)
        self.assertEqual(recovered["nome"], "[PREFEITURA] - Ônibus - Camutanga / PE")
        self.assertEqual(recovered["data_original"], "28/08/2026")
        self.assertEqual(recovered["hora_marcador"], "04:00")
        self.assertEqual(recovered["endereco_ou_localizacao"], "Av. Presidente Getúlio Vargas")

    def test_recupera_titulo_de_registro_importado_sem_data(self) -> None:
        data = {
            "TITULO;DATA;MARCADOR;DESCRIÇÃO;LOCALIZAÇÃO": "[PREFEITURA] - Veículos"
        }
        self.assertEqual(
            atualizador.embedded_semicolon_event(data)["nome"],
            "[PREFEITURA] - Veículos",
        )

    def test_pipeline_preserva_data_do_google_my_maps(self) -> None:
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        self.assertIn('"--sem-editais"', source)

    def test_remove_lote_de_data_passada(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertFalse(indexador.upcoming_lot({"data": "2026-07-13", "hora": "18:00"}, now))
        self.assertTrue(indexador.upcoming_lot({"data": "2026-07-15", "hora": "08:00"}, now))

    def test_site_preserva_lotes_distintos_com_link_compartilhado(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        shared = "https://exemplo.com/leilao/1"
        lots = [
            {
                "evento": "Leilão teste",
                "data": "2026-12-31",
                "lote": "01",
                "titulo": "Lote 01 - Escavadeira",
                "link_lote": shared,
            },
            {
                "evento": "Leilão teste",
                "data": "2026-12-31",
                "lote": "02",
                "titulo": "Lote 02 - Caminhão",
                "link_lote": shared,
            },
        ]
        events = [{"nome": "Leilão teste", "data": "2026-12-31", "link": shared}]
        result = site.enrich_and_dedupe_lots(lots, events, now)
        self.assertEqual([row["lote"] for row in result], ["01", "02"])
        self.assertTrue(all(row.get("evento_id", "").startswith("evento-") for row in result))

    def test_site_preserva_marcadores_iguais_com_ids_diferentes(self) -> None:
        base = {
            "nome": "Leilão teste",
            "data": "2026-12-31",
            "hora_marcador": "10:00",
            "link": "https://exemplo.com/leilao/1",
        }
        prepared = site.prepare_events([
            {**base, "id_marcador_mapa": "marcador-1"},
            {**base, "id_marcador_mapa": "marcador-2"},
        ])
        self.assertEqual(len({row["evento_id"] for row in prepared}), 2)

    def test_site_diferencia_mesmo_evento_em_horarios_distintos(self) -> None:
        base = {
            "nome": "Leilão teste",
            "data": "2026-12-31",
            "link": "https://exemplo.com/leilao/1",
        }
        prepared = site.prepare_events([
            {**base, "hora_marcador": "04:00"},
            {**base, "hora_marcador": "05:00"},
        ])
        self.assertEqual(len({row["evento_id"] for row in prepared}), 2)

    def test_site_remove_repeticao_do_mesmo_lote(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        lot = {
            "evento": "Leilão teste",
            "data": "2026-12-31",
            "lote": "01",
            "titulo": "Lote 01 - Escavadeira",
            "link_lote": "https://exemplo.com/leilao/1",
        }
        events = [{"nome": "Leilão teste", "data": "2026-12-31", "link": lot["link_lote"]}]
        result = site.enrich_and_dedupe_lots([lot, dict(lot)], events, now)
        self.assertEqual(len(result), 1)

    def test_site_descarta_lote_sem_evento_no_mapa(self) -> None:
        now = datetime(2026, 7, 14, 16, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        events = [{
            "nome": "Leilão do mapa",
            "data": "2026-12-31",
            "link": "https://exemplo.com/evento-do-mapa",
        }]
        lots = [
            {
                "evento": "Leilão do mapa",
                "data": "2026-12-31",
                "titulo": "Escavadeira cadastrada",
                "link_evento": "https://exemplo.com/evento-do-mapa",
            },
            {
                "evento": "Leilão descoberto fora do mapa",
                "data": "2026-12-31",
                "titulo": "Lote externo",
                "link_evento": "https://externo.test/evento",
            },
        ]
        result = site.enrich_and_dedupe_lots(lots, events, now)
        self.assertEqual([row["titulo"] for row in result], ["Escavadeira cadastrada"])

    def test_site_carrega_somente_a_base_indexada_do_mapa(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lotes.json"
            path.write_text(
                '{"lotes":[{"data":"2026-12-31","titulo":"Escavadeira do mapa"}]}',
                encoding="utf-8",
            )
            with mock.patch.object(site, "ROOT", Path(directory)):
                rows = site.read_lotes()
        self.assertEqual(rows[0]["titulo"], "Escavadeira do mapa")

    def test_pipeline_usa_exclusivamente_eventos_do_mapa(self) -> None:
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        root = Path(pipeline.__file__).resolve().parent
        workflow = (root / ".github/workflows/atualizar-radar.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            pipeline.MAP_EVENTS_FILE,
            "radar_leiloes_eventos_futuros.csv",
        )
        self.assertEqual(pipeline.EVENT_SOURCE, "google_my_maps")
        self.assertNotIn('"descobrir_leiloes_web.py"', source)
        self.assertNotIn("descobrir_leiloes_web.py", workflow)
        self.assertNotIn("OPENAI_API_KEY", workflow)
        self.assertFalse(
            (root / ".github/workflows/descoberta-profunda.yml").exists()
        )

    def test_limpeza_remove_lote_que_nao_pertence_ao_mapa(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "eventos.csv"
            lots_path = root / "lotes.json"
            lots_csv_path = root / "lotes.csv"
            events_path.write_text(
                "nome,data,link,site_leiloeiro,link_edital,descricao\n"
                "Leilão do mapa,2026-12-31,https://exemplo.com/mapa,,,\n",
                encoding="utf-8",
            )
            lots_path.write_text(
                json.dumps(
                    {
                        "lotes": [
                            {
                                "evento": "Leilão do mapa",
                                "data": "2026-12-31",
                                "titulo": "Escavadeira do mapa",
                                "link_evento": "https://exemplo.com/mapa",
                            },
                            {
                                "evento": "Evento externo",
                                "data": "2026-12-31",
                                "titulo": "Lote externo",
                                "link_evento": "https://externo.test/evento",
                            },
                        ],
                        "logs": [
                            {
                                "evento": "Leilão do mapa",
                                "data": "2026-12-31",
                                "status": "html_ok",
                            },
                            {
                                "evento": "Evento externo",
                                "data": "2026-12-31",
                                "status": "html_ok",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            total = indexador.clean_existing_outputs(
                lots_path,
                lots_csv_path,
                events_path,
            )
            payload = json.loads(lots_path.read_text(encoding="utf-8"))

        self.assertEqual(total, 1)
        self.assertEqual(payload["total_lotes"], 1)
        self.assertEqual(payload["lotes"][0]["titulo"], "Escavadeira do mapa")
        self.assertEqual(len(payload["logs"]), 1)
        self.assertEqual(payload["lotes_descartados_fora_do_mapa"], 1)
        self.assertTrue(payload["somente_eventos_do_mapa"])

    def test_diagnostico_confere_fonte_embutida_no_site(self) -> None:
        payload = diagnostico.embedded_radar_data(
            '<script type="application/json" id="radar-data">'
            '{"fonte_eventos":"Google My Maps",'
            '"somente_eventos_do_mapa":true,"lotes":[]}'
            '</script>'
        )
        self.assertEqual(payload["fonte_eventos"], "Google My Maps")
        self.assertTrue(payload["somente_eventos_do_mapa"])

    def test_site_oferece_hoje_amanha_e_data_especifica(self) -> None:
        personalized = apply_date_highlights(site.TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn('data-date-shortcut="today"', personalized)
        self.assertIn('data-date-shortcut="tomorrow"', personalized)
        self.assertIn('id="exact-date-filter"', personalized)
        self.assertIn("exactDate:''", personalized)
        self.assertIn("row.data!==state.exactDate", personalized)
        self.assertIn("state.exactDate===value&&source!=='calendar'", personalized)

    def test_site_identifica_municipio_e_adiciona_coordenadas(self) -> None:
        row = {"uf": "MG", "local": "Taiobeiras - MG"}
        municipalities = site.municipality_index(
            [["Taiobeiras", "MG", -15.8106, -42.2259]]
        )
        site.add_municipality_coordinates(row, {}, municipalities)
        self.assertEqual(row["cidade"], "Taiobeiras")
        self.assertEqual((row["latitude"], row["longitude"]), (-15.8106, -42.2259))

    def test_site_recupera_uf_a_partir_do_local_do_lote(self) -> None:
        self.assertEqual(site.infer_uf("Quirinópolis - GO, Goiás"), "GO")

    def test_site_oferece_filtro_por_cidade_e_raio(self) -> None:
        personalized = apply_date_highlights(site.TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn('id="location-input"', personalized)
        self.assertIn('id="radius-filter"', personalized)
        self.assertIn('id="use-location"', personalized)
        self.assertIn("function distanceKm(row)", personalized)
        self.assertIn("distance>state.radius", personalized)
        self.assertIn(".slice(0,20)", personalized)
        self.assertNotIn("municipalityOptionsLoaded", personalized)

    def test_site_mostra_leilao_antes_dos_lotes(self) -> None:
        personalized = apply_date_highlights(site.TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn("function groupAuctions(eventRows,lotRows)", personalized)
        self.assertIn("const allGroups=groupAuctions(events,lots)", personalized)
        self.assertIn('class="auction-group"', personalized)
        self.assertIn('data-toggle-auction=', personalized)
        self.assertIn("expandedAuctions", personalized)
        self.assertIn("MOSTRAR MAIS LOTES", personalized)
        self.assertIn("LOTES NO SITE OFICIAL", personalized)
        self.assertIn("data-open-auction", personalized)
        self.assertIn("registros do mapa", personalized)

    def test_site_publica_todos_os_registros_do_mapa(self) -> None:
        source = Path(site.__file__).read_text(encoding="utf-8")
        personalized = apply_date_highlights(site.TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn('read_csv("radar_leiloes_base_completa.csv")', source)
        self.assertIn("const events=await fetch", personalized)
        self.assertIn('"radar_eventos_site.json"', source)
        self.assertIn('value="past">Já realizados', personalized)
        self.assertIn('value="undated">Sem data informada', personalized)

    def test_site_oferece_escolha_entre_leiloes_e_licitacoes(self) -> None:
        portal = site.PORTAL_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('href="./leiloes.html"', portal)
        self.assertIn('href="./licitacoes.html"', portal)
        self.assertIn("Radar de Oportunidades", portal)

    def test_site_remove_marca_anterior_e_oferece_contato(self) -> None:
        templates = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (site.TEMPLATE, site.PORTAL_TEMPLATE, site.LICITACOES_TEMPLATE)
        )
        self.assertNotRegex(templates.casefold(), r"g[ -]?m[aá]quina")
        self.assertIn("mailto:contato@empaez.com", templates)
        self.assertIn("Falar pelo WhatsApp", templates)
        self.assertNotIn("5538998465955", templates)

    def test_licitacao_mapeia_dados_oficiais_e_link_do_pncp(self) -> None:
        row = licitacoes.map_contract(
            {
                "numeroControlePNCP": "00394502000144-1-000180/2026",
                "numeroCompra": "18/2026",
                "processo": "123/2026",
                "objetoCompra": "Aquisição de máquinas",
                "modalidadeId": 6,
                "modalidadeNome": "Pregão - Eletrônico",
                "dataEncerramentoProposta": "2026-08-10T10:00:00",
                "valorTotalEstimado": 100000,
                "orgaoEntidade": {"razaoSocial": "Órgão de Teste"},
                "unidadeOrgao": {"nomeUnidade": "Unidade Central", "ufSigla": "MG", "municipioNome": "Taiobeiras"},
            }
        )
        self.assertEqual(row["uf"], "MG")
        self.assertEqual(row["cidade"], "Taiobeiras")
        self.assertEqual(row["orgao"], "Órgão de Teste")
        self.assertEqual(row["link"], "https://pncp.gov.br/app/editais/00394502000144/2026/180")

    def test_coletor_de_licitacoes_pagina_todas_as_modalidades(self) -> None:
        calls = []

        def fake_request(final_date: str, page: int) -> dict:
            calls.append(page)
            return {"data": [], "totalPaginas": 3}

        with mock.patch.object(licitacoes, "request_page", side_effect=fake_request):
            rows, errors, truncated = licitacoes.collect(
                datetime(2026, 8, 4, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
            )
        self.assertEqual(rows, [])
        self.assertEqual(errors, [])
        self.assertFalse(truncated)
        self.assertEqual(set(calls), {1, 2, 3})

    def test_coletor_usa_publicacoes_quando_propostas_falha(self) -> None:
        raw = {
            "numeroControlePNCP": "00394502000144-1-000180/2026",
            "objetoCompra": "Aquisição de máquinas e equipamentos",
            "modalidadeId": 6,
            "modalidadeNome": "Pregão - Eletrônico",
            "dataEncerramentoProposta": "2026-08-20T10:00:00",
            "orgaoEntidade": {"razaoSocial": "Órgão de Teste"},
            "unidadeOrgao": {"ufSigla": "MG", "municipioNome": "Taiobeiras"},
        }
        with mock.patch.object(licitacoes, "request_page", side_effect=RuntimeError("indisponível")), mock.patch.object(
            licitacoes, "request_publication_page", return_value={"data": [raw], "totalPaginas": 1}
        ), mock.patch.object(licitacoes, "PUBLICATION_LOOKBACK_DAYS", 0), mock.patch.object(
            licitacoes, "PUBLICATION_MODALITIES", (6,)
        ):
            rows, errors, truncated = licitacoes.collect(
                datetime(2026, 8, 4, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fonte"], "PNCP")
        self.assertTrue(errors)
        self.assertFalse(truncated)

    def test_compras_gov_mapeia_formato_plano_e_filtra_prazo(self) -> None:
        raw = {
            "numeroControlePNCP": "00394502000144-1-000180/2026",
            "numeroCompra": "18/2026",
            "orgaoEntidadeRazaoSocial": "Órgão de Teste",
            "unidadeOrgaoNomeUnidade": "Unidade Central",
            "unidadeOrgaoUfSigla": "MG",
            "unidadeOrgaoMunicipioNome": "Taiobeiras",
            "objetoCompra": "Aquisição de máquinas",
            "modalidadeNome": "Pregão - Eletrônico",
            "dataEncerramentoPropostaPncp": "2026-08-20T10:00:00",
        }
        with mock.patch.object(
            licitacoes,
            "request_compras_gov_page",
            return_value={"resultado": [raw], "totalPaginas": 1},
        ), mock.patch.object(licitacoes, "COMPRAS_GOV_MODALITIES", (5,)):
            rows, errors, truncated = licitacoes.collect_compras_gov(
                datetime(2026, 8, 4, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
            )
        self.assertEqual((len(rows), errors, truncated), (1, [], False))
        self.assertEqual(rows[0]["fonte"], "Compras.gov.br")
        self.assertEqual(rows[0]["cidade"], "Taiobeiras")

    def test_openai_aceita_somente_licitacao_com_fonte_e_prazo_futuro(self) -> None:
        sources = [{"url": "https://prefeitura.gov.br/licitacoes/123", "title": "Edital 123"}]
        raw = [{
            "id": None,
            "numero": "123/2026",
            "processo": None,
            "orgao": "Prefeitura de Teste",
            "unidade": None,
            "objeto": "Locação de máquinas pesadas para manutenção de estradas",
            "modalidade": "Pregão eletrônico",
            "data_publicacao": "2026-08-01",
            "data_abertura": None,
            "data_encerramento": "2026-08-20T10:00:00",
            "valor_estimado": 250000,
            "uf": "MG",
            "cidade": "Taiobeiras",
            "link": "https://prefeitura.gov.br/licitacoes/123",
        }]
        rows, rejected = licitacoes_openai.validate_rows(raw, sources, datetime(2026, 8, 4).date())
        self.assertEqual((len(rows), rejected), (1, 0))
        self.assertTrue(rows[0]["origem_validada"])
        self.assertEqual(rows[0]["fonte"], "OpenAI Web Search")

    def test_openai_rejeita_link_nao_consultado_e_prazo_encerrado(self) -> None:
        base = {
            "id": None, "numero": None, "processo": None, "orgao": "Órgão de Teste",
            "unidade": None, "objeto": "Aquisição de equipamentos diversos", "modalidade": None,
            "data_publicacao": None, "data_abertura": None, "valor_estimado": None,
            "uf": "MG", "cidade": None,
        }
        raw = [
            {**base, "data_encerramento": "2026-08-20", "link": "https://inventado.test/1"},
            {**base, "data_encerramento": "2026-08-01", "link": "https://fonte.gov.br/1"},
        ]
        rows, rejected = licitacoes_openai.validate_rows(
            raw, [{"url": "https://fonte.gov.br/1", "title": "Edital"}], datetime(2026, 8, 4).date()
        )
        self.assertEqual(rows, [])
        self.assertEqual(rejected, 2)

    def test_licitacoes_rejeitam_e_nao_preservam_leiloes(self) -> None:
        row = {
            "id": "1", "numero": None, "processo": None, "orgao": "Órgão de Teste",
            "unidade": None, "objeto": "Leilão de veículos conservados", "modalidade": "Leilão",
            "data_publicacao": None, "data_abertura": None, "data_encerramento": "2026-08-20",
            "valor_estimado": None, "uf": "BA", "cidade": None,
            "link": "https://fonte.gov.br/leilao/1",
        }
        accepted, rejected = licitacoes_openai.validate_rows(
            [row], [{"url": row["link"], "title": "Edital"}], datetime(2026, 8, 4).date()
        )
        self.assertEqual((accepted, rejected), ([], 1))
        self.assertEqual(licitacoes.open_rows([row], datetime(2026, 8, 4).date()), [])

    def test_busca_openai_usa_web_search_obrigatoria_e_schema_estrito(self) -> None:
        response = {
            "output_text": json.dumps({"licitacoes": []}),
            "output": [{"type": "web_search_call", "action": {"sources": []}}],
        }
        client = mock.Mock()
        client.responses.create.return_value = response
        with mock.patch.object(licitacoes_openai, "national_queries", return_value=[("MG", "consulta")]), mock.patch.dict(
            os.environ, {"OPENAI_API_KEY": "segredo", "OPENAI_SEARCH_MODEL": "gpt-test"}, clear=True
        ):
            rows, report = licitacoes_openai.collect_openai(
                datetime(2026, 8, 4, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")), client=client
            )
        self.assertEqual(rows, [])
        self.assertEqual(report["consultas_executadas"], 1)
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["tools"], [{"type": "web_search"}])
        self.assertEqual(kwargs["tool_choice"], "required")
        self.assertTrue(kwargs["text"]["format"]["strict"])
        self.assertFalse(kwargs["store"])

    def test_licitacoes_mesclam_base_anterior_openai_e_pncp(self) -> None:
        previous = {"id": "1", "objeto": "Antigo", "data_encerramento": "2026-08-20", "fonte": "Anterior"}
        openai = {**previous, "objeto": "Objeto corrigido", "fonte": "OpenAI Web Search"}
        pncp = {**openai, "orgao": "Órgão oficial", "fonte": "PNCP"}
        rows = licitacoes.merge_rows([previous], [openai], [pncp])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fonte"], "PNCP")
        self.assertEqual(rows[0]["orgao"], "Órgão oficial")

    def test_licitacoes_deduplicam_fontes_pelo_mesmo_link(self) -> None:
        openai = {
            "id": "", "link": "https://pncp.gov.br/app/editais/123/2026/1", "orgao": "Órgão",
            "objeto": "Compra de máquina", "data_encerramento": "2026-08-20", "fonte": "OpenAI Web Search",
        }
        pncp = {**openai, "id": "123-1-000001/2026", "fonte": "PNCP"}
        rows = licitacoes.merge_rows([openai], [pncp])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fonte"], "PNCP")

    def test_corrige_acentos_corrompidos_do_mapa(self) -> None:
        original = "[ﾃ迭Gﾃグ Pﾃ咤LICO] - Veﾃｭculos, ﾃ馬ibus e Mﾃ｡quinas - Sﾃ｣o Paulo"
        self.assertEqual(
            corrigir_texto(original),
            "[ÓRGÃO PÚBLICO] - Veículos, Ônibus e Máquinas - São Paulo",
        )

    def test_corrige_campos_do_mapa_com_caractere_perdido(self) -> None:
        payload = {
            "DESCRIﾃ�ﾃグ": "Leilﾃ｣o de CAﾃ�AMBAS",
            "LOCALIZAﾃ�ﾃグ": "Capﾃ｣o do Leﾃ｣o - RS",
        }
        corrected = corrigir_dados(payload)
        self.assertEqual(corrected["DESCRIÇÃO"], "Leilão de CAÇAMBAS")
        self.assertEqual(corrected["LOCALIZAÇÃO"], "Capão do Leão - RS")
        self.assertFalse(tem_codificacao_corrompida(str(corrected)))

    def test_preserva_portugues_ja_correto(self) -> None:
        text = "Leilão de máquinas em Águas de Santa Bárbara — São Paulo"
        self.assertEqual(corrigir_texto(text), text)

    def test_corrige_unidade_de_volume_com_caractere_perdido(self) -> None:
        self.assertEqual(corrigir_texto("Compactador com caixa de 19m�"), "Compactador com caixa de 19m³")

    def test_mascara_chave_aws_encontrada_em_conteudo_externo(self) -> None:
        fake_key = "AKIA" + "A" * 16
        sanitized, replacements = sanitizer.sanitize_text(f"Lote {fake_key}")
        self.assertEqual(replacements, 1)
        self.assertNotIn(fake_key, sanitized)
        self.assertIn(sanitizer.REPLACEMENT, sanitized)

    def test_relatorio_compara_chaves_estaveis(self) -> None:
        anterior = [{"link_lote": "https://exemplo.com/lote/1", "titulo": "Lote 1"}]
        atual = [{"link_lote": "https://exemplo.com/lote/2", "titulo": "Lote 2"}]
        logs = [{"link": "https://exemplo.com/leilao", "status": "html_ok", "lotes": 1, "fontes_tentadas": []}]
        report = indexador.build_update_report(anterior, atual, atual, logs, 0)
        self.assertEqual(report["lotes_antes"], 1)
        self.assertEqual(report["lotes_depois"], 1)
        self.assertEqual(report["lotes_realmente_novos"], 1)
        self.assertEqual(report["lotes_removidos_ou_encerrados"], 1)
        self.assertEqual(report["eventos_com_lotes"], 1)

    def test_relatorio_detecta_portais_bloqueados_e_falhas(self) -> None:
        logs = [{
            "link": "https://bloqueado.com/leilao",
            "status": "bloqueado_http_403",
            "lotes": 0,
            "fontes_tentadas": [{"url": "https://bloqueado.com/leilao", "status": "bloqueado_http_403", "http": 403, "lotes": 0}],
        }]
        report = indexador.build_update_report([], [], [], logs, 0)
        self.assertEqual(report["eventos_bloqueados"], 1)
        self.assertEqual(report["eventos_com_erro"], 1)
        self.assertEqual(report["erros_por_leiloeiro"], {"bloqueado.com": 1})
        self.assertEqual(report["urls_que_falharam"][0]["http"], 403)

    def test_preservacao_restaura_base_anterior(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup = root / "backup"
            backup.mkdir()
            base = root / "lotes.json"
            base.write_text('{"total_lotes": 10}', encoding="utf-8")
            with mock.patch.object(pipeline, "ROOT", root), mock.patch.object(
                pipeline,
                "GENERATED_FILES",
                ["lotes.json"],
            ):
                pipeline.backup_generated_files(backup)
                base.write_text('{"total_lotes": 0}', encoding="utf-8")
                pipeline.restore_generated_files(backup)
            self.assertEqual(
                base.read_text(encoding="utf-8"),
                '{"total_lotes": 10}',
            )


if __name__ == "__main__":
    unittest.main()
