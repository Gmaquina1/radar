from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import descobrir_leiloes_web as discovery
from coletores.generico import GenericCollector, canonicalize_url
from web_search.base import SearchResult
from web_search.provider import search_web
from web_search.openai_provider import OpenAIProvider, response_sources
from auditar_cobertura import audit, matches
from openai_preflight import check, classify_error


JSONLD = '''<html><head><script type="application/ld+json">{"@type":"Product","name":"Lote 7 - Trator","description":"Trator agrícola","url":"/lote/7","image":"/7.jpg","offers":{"price":"90000"}}</script></head><body><a href="/evento/2">Evento</a></body></html>'''
OG = '<meta property="og:title" content="Leilão Público"><meta property="og:image" content="/foto.jpg"><a href="/lotes">Lotes</a>'


class FakeClient:
    def __init__(self, page=JSONLD, status=200): self.page, self.status, self.calls = page, status, []
    def get(self, url):
        self.calls.append(url)
        if url.endswith("robots.txt"): return "Sitemap: https://novo.test/map.xml", url, 200, {}
        if url.endswith("map.xml"): return '<urlset><url><loc>https://novo.test/leilao/1</loc></url></urlset>', url, 200, {}
        if "sitemap" in url: return "", url, 404, {}
        return (self.page if self.status == 200 else ""), url, self.status, {"Retry-After": "2"}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.paths = {name: root / name for name in ("catalog.json", "new.json", "state.json", "events.json", "all.csv", "report.json", "coverage.json", "map.csv")}
        self.paths["map.csv"].write_text("nome,link\n", encoding="utf-8")
        self.stack = patch.multiple(discovery, CATALOG=self.paths["catalog.json"], NEW_CATALOG=self.paths["new.json"], STATE=self.paths["state.json"], EVENTS=self.paths["events.json"], CONSOLIDATED=self.paths["all.csv"], REPORT=self.paths["report.json"], COVERAGE=self.paths["coverage.json"])
        self.stack.start(); self.addCleanup(self.stack.stop); self.addCleanup(self.tmp.cleanup)

    def execute(self, client=None, deep=False):
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "openai", "OPENAI_API_KEY": "secret", "OPENAI_SEARCH_IN_QUICK": "1"}, clear=False):
            return discovery.run(deep, client or FakeClient(), lambda *args: [SearchResult("https://novo.test/leilao/1")], self.paths["map.csv"])

    def test_mapa_vazio_descobre_evento_e_lote(self):
        result = self.execute(); self.assertGreater(result["eventos_descobertos"], 0); self.assertGreater(result["lotes_descobertos"], 0)
    def test_portal_novo_persistido(self):
        self.execute(); self.assertEqual(json.loads(self.paths["catalog.json"].read_text())[0]["dominio"], "novo.test")
    def test_novo_portal_tem_status(self):
        self.execute(); self.assertEqual(json.loads(self.paths["new.json"].read_text())[0]["status"], "pendente")
    def test_portal_conhecido_revisitado_sem_busca(self):
        self.paths["catalog.json"].write_text('[{"dominio":"novo.test","ativo":true,"url_exemplo":"https://novo.test/leilao/1"}]')
        with patch.dict(os.environ, {}, clear=True):
            result = discovery.run(client=FakeClient(), search=lambda *a: [], map_path=self.paths["map.csv"])
        self.assertGreater(result["eventos_descobertos"], 0)

    def test_modo_rapido_limita_portais_e_nao_faz_busca_openai(self):
        self.paths["catalog.json"].write_text(json.dumps([
            {"dominio":"a.test","ativo":True,"url_exemplo":"https://a.test/leilao"},
            {"dominio":"b.test","ativo":True,"url_exemplo":"https://b.test/leilao"},
        ]))
        calls = []
        with patch.dict(os.environ, {}, clear=True), patch.dict(
            discovery.CONFIG,
            {"FAST_MAX_PORTALS": 1},
            clear=False,
        ):
            result = discovery.run(
                deep=False,
                client=FakeClient(),
                search=lambda *args: calls.append(args),
                map_path=self.paths["map.csv"],
            )
        self.assertEqual(result["modo"], "rapido")
        self.assertEqual(result["portais_planejados"], 1)
        self.assertEqual(result["consultas_executadas"], 0)
        self.assertEqual(calls, [])

    def test_modo_profundo_usa_busca_e_catalogo(self):
        self.paths["catalog.json"].write_text(
            '[{"dominio":"catalogo.test","ativo":true,'
            '"url_exemplo":"https://catalogo.test/leilao"}]'
        )
        with patch.dict(
            os.environ,
            {
                "WEB_SEARCH_PROVIDER": "openai",
                "OPENAI_API_KEY": "secret",
            },
            clear=True,
        ), patch.object(
            discovery,
            "query_group",
            return_value=("A", ["consulta teste"]),
        ):
            result = discovery.run(
                deep=True,
                client=FakeClient(),
                search=lambda *args: [SearchResult("https://novo.test/leilao")],
                map_path=self.paths["map.csv"],
            )
        self.assertEqual(result["modo"], "profundo")
        self.assertEqual(result["consultas_executadas"], 1)
        self.assertGreaterEqual(result["dominios_visitados"], 2)
    def test_erro_de_um_dominio_nao_interrompe(self):
        result = self.execute(FakeClient(status=403)); self.assertEqual(result["bloqueados"], 1)
    def test_relatorio_indica_api_ausente(self):
        with patch.dict(os.environ, {}, clear=True):
            result = discovery.run(client=FakeClient(), search=lambda *a: [], map_path=self.paths["map.csv"])
        self.assertFalse(result["busca_web_configurada"])
        self.assertEqual(result["consultas_executadas"], 0)
    def test_relatorio_registra_configuracao_e_metricas_da_busca(self):
        result = self.execute()
        self.assertTrue(result["busca_web_configurada"])
        self.assertEqual(result["web_search_provider"], "openai")
        self.assertGreater(result["consultas_executadas"], 0)
        self.assertEqual(result["resultados_de_busca"], result["consultas_executadas"])
        self.assertNotIn("WEB_SEARCH_API_KEY", result)
    def test_deep_discovery(self):
        result = self.execute(deep=True); self.assertIn(result["grupo_consultas"], "ABCD")
    def test_rotacao(self):
        a, _ = discovery.query_group(self.paths["state.json"]); b, _ = discovery.query_group(self.paths["state.json"]); self.assertEqual((a, b), ("A", "B"))
    def test_todas_ufs_distribuidas(self): self.assertEqual(len(discovery.UFS), 27)
    def test_sitemap(self):
        urls, indexes = discovery.sitemap_urls('<urlset><url><loc>https://x.test/lote/1</loc></url></urlset>'); self.assertEqual(urls, ["https://x.test/lote/1"]); self.assertFalse(indexes)
    def test_sitemap_index(self):
        urls, indexes = discovery.sitemap_urls('<sitemapindex><sitemap><loc>https://x.test/s.xml</loc></sitemap></sitemapindex>'); self.assertFalse(urls); self.assertEqual(len(indexes), 1)
    def test_sitemap_gzip(self):
        import gzip
        raw = gzip.compress(b'<urlset><url><loc>https://x.test/lote/1</loc></url></urlset>')
        self.assertEqual(discovery.sitemap_urls(raw)[0], ["https://x.test/lote/1"])
    def test_robots(self): self.assertEqual(discovery.robots_sitemaps("User-agent: *\nSitemap: https://x.test/s.xml"), ["https://x.test/s.xml"])
    def test_retry_after(self): self.assertEqual(discovery.retry_seconds("12"), 12)
    def test_canonical_remove_tracking(self): self.assertEqual(canonicalize_url("http://www.X.test/lote/1/?utm_source=a&id=7#foto"), "https://x.test/lote/1?id=7")
    def test_canonical_preserva_paginacao(self): self.assertIn("page=2", canonicalize_url("https://x.test/lotes?page=2"))
    def test_json_ld(self):
        lots, _ = GenericCollector().parse_html("https://x.test/evento", JSONLD); self.assertEqual(lots[0]["titulo"], "Lote 7 - Trator"); self.assertEqual(lots[0]["confianca_dados"], "alta")
    def test_json_ld_foto(self): self.assertEqual(GenericCollector().parse_html("https://x.test/evento", JSONLD)[0][0]["foto_lote"], "https://x.test/7.jpg")
    def test_open_graph(self):
        lots, _ = GenericCollector().parse_html("https://x.test", OG); self.assertEqual(lots[0]["titulo"], "Leilão Público")
    def test_sem_foto_nao_inventa(self):
        lots, _ = GenericCollector().parse_html("https://x.test", '<meta property="og:title" content="Lote">'); self.assertEqual(lots[0]["foto_lote"], "")
    def test_links_internos_relevantes(self):
        _, links = GenericCollector().parse_html("https://x.test", '<a href="/contato">x</a><a href="/lotes">y</a>'); self.assertEqual(links, ["https://x.test/lotes"])
    def test_itemlist(self):
        page = '<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"item":{"@type":"Product","name":"Sem número"}}]}</script>'
        lots, _ = GenericCollector().parse_html("https://x.test", page); self.assertEqual(lots[0]["titulo"], "Sem número")
    def test_status_desconhecido(self): self.assertEqual(GenericCollector().parse_html("https://x.test", JSONLD)[0][0]["status_evento"], "desconhecido")
    def test_provider_sem_chave(self):
        with patch.dict(os.environ, {}, clear=True): self.assertEqual(search_web("leilão"), [])
    def test_consolidacao_deduplica_url(self):
        rows = [{"nome":"A", "link":"https://x.test/lote?utm_source=a"}, {"nome":"B", "link":"https://x.test/lote"}]
        discovery.consolidate([], rows, self.paths["all.csv"]); self.assertEqual(len(self.paths["all.csv"].read_text().splitlines()), 2)

    def test_urls_malformadas_sao_ignoradas(self):
        for value in (None, "", "   ", "https://x.test:porta/lote", "/relativa", "não é url"):
            self.assertEqual(canonicalize_url(value), "")
        self.assertEqual(canonicalize_url("/lote#foto", "https://x.test/evento"), "https://x.test/lote")
        self.assertEqual(canonicalize_url("https://x.test/a https://y.test/b"), "https://x.test/a")

    def test_jsonld_formatos_permissivos(self):
        page = '<script type="application/ld+json">{"@graph":[{"@type":["Thing","Product"],"name":"X","url":{"@id":"/x"},"image":[{"url":"/x.jpg"}],"offers":[{"price":3}]},{"@type":"Product","name":"Y","url":null,"image":null}]}</script>'
        lots, _ = GenericCollector().parse_html("https://x.test/e", page)
        self.assertEqual((lots[0]["link_lote"], lots[0]["foto_lote"], lots[0]["lance_atual"]), ("https://x.test/x", "https://x.test/x.jpg", 3))
        self.assertEqual(lots[1]["link_lote"], "https://x.test/e")

    def test_jsonld_e_html_invalidos(self):
        lots, links = GenericCollector().parse_html("https://x.test", '<script type="application/ld+json">{ruim</script><a href="https://x.test:bad/lote">')
        self.assertEqual((lots, links), ([], []))

    def test_bootstrap_catalogo_vazio(self):
        source = self.paths["map.csv"]
        source.write_text("nome,site_leiloeiro\nA,https://portal.test/leilao/1\n", encoding="utf-8")
        result = discovery.bootstrap_portais(self.paths["catalog.json"], [source])
        self.assertEqual(result[0]["dominio"], "portal.test")

    def test_timeout_isolado_e_segundo_dominio_continua(self):
        self.paths["catalog.json"].write_text('[{"dominio":"ruim.test","ativo":true,"url_exemplo":"https://ruim.test/"},{"dominio":"novo.test","ativo":true,"url_exemplo":"https://novo.test/leilao"}]')
        class Client(FakeClient):
            def get(self, url):
                if "ruim.test" in url: raise TimeoutError("demorou")
                return super().get(url)
        with patch.dict(os.environ, {}, clear=True): result = discovery.run(client=Client(), search=lambda *a: [], map_path=self.paths["map.csv"])
        self.assertGreater(result["eventos_descobertos"], 0)
        self.assertTrue(any(e["dominio"] == "ruim.test" and e["tipo_erro"] == "TimeoutError" for e in result["erros"]))

    def test_orcamento_por_dominio_interrompe_portal_lento(self):
        self.paths["catalog.json"].write_text(
            '[{"dominio":"lento.test","ativo":true,'
            '"url_exemplo":"https://lento.test/leilao"},'
            '{"dominio":"novo.test","ativo":true,'
            '"url_exemplo":"https://novo.test/leilao"}]'
        )

        class Client(FakeClient):
            def get(self, url):
                if "lento.test" in url:
                    raise discovery.DomainBudgetExceeded("limite")
                return super().get(url)

        with patch.dict(os.environ, {}, clear=True):
            result = discovery.run(
                client=Client(),
                search=lambda *args: [],
                map_path=self.paths["map.csv"],
            )
        self.assertEqual(result["timeouts"], 1)
        self.assertGreater(result["eventos_descobertos"], 0)

    def test_execucao_parcial_preserva_eventos_anteriores(self):
        self.paths["events.json"].write_text(json.dumps({
            "eventos": [{
                "nome": "Evento anterior",
                "link": "https://antigo.test/leilao/1",
                "site_leiloeiro": "https://antigo.test/leilao/1",
                "dominio_origem": "antigo.test",
            }],
            "lotes": [],
        }))
        self.paths["catalog.json"].write_text(
            '[{"dominio":"novo.test","ativo":true,'
            '"url_exemplo":"https://novo.test/leilao"}]'
        )
        with patch.dict(os.environ, {}, clear=True):
            result = discovery.run(
                client=FakeClient(),
                search=lambda *args: [],
                map_path=self.paths["map.csv"],
            )
        saved = json.loads(self.paths["events.json"].read_text())
        self.assertEqual(result["eventos_preservados"], 1)
        self.assertTrue(
            any(
                row.get("site_leiloeiro") == "https://antigo.test/leilao/1"
                for row in saved["eventos"]
            )
        )

    def test_http_429_registrado(self):
        result = self.execute(FakeClient(status=429))
        self.assertTrue(any(e["http_status"] == 429 for e in result["erros"]))

    def test_sitemap_invalido(self):
        self.assertEqual(discovery.sitemap_urls("<xml"), ([], []))

    def test_busca_garra_florestal_plural_e_caixa(self):
        rows = [{"titulo":"01 GARRA FLORESTAL"}, {"titulo":"02 GARRAS FLORESTAIS"}]
        for term in ("garra florestal", "garra", "florestal", "garras florestais", "GARRA FLORESTAL"):
            self.assertEqual(sum(matches(row, term) for row in rows), 2)

    def test_auditoria_web_faz_duas_consultas_sem_alterar_base(self):
        base = self.paths["events.json"]
        base.write_text('{"lotes":[{"titulo":"Garra florestal","link_lote":"https://base.test/1"}]}')
        before = base.read_text()
        calls = []
        def search(query, page, limit):
            calls.append(query); return [SearchResult("https://web.test/2")]
        result = audit("garra florestal", base, search, web=True)
        self.assertEqual(calls, ["garra florestal leilão", "garra florestal lote leilão"])
        self.assertEqual((result["RESULTADOS_WEB"], result["RESULTADOS_NA_BASE"], result["POSSIVEIS_AUSENTES"]), (1, 1, 1))
        self.assertEqual(base.read_text(), before)


class OpenAIProviderTests(unittest.TestCase):
    def response(self):
        return {"output": [
            {"type": "web_search_call", "action": {"sources": [
                {"url": "https://a.test/leilao", "title": "A"},
                {"url": "https://a.test/leilao", "title": "duplicado"},
                {"url": "javascript:alert(1)", "title": "inválido"},
            ]}},
            {"type": "message", "content": [{"annotations": [
                {"type": "url_citation", "url": "https://b.test/lote", "title": "B"}
            ]}]},
        ]}

    def test_web_search_call_multiplas_fontes_deduplica_e_valida(self):
        self.assertEqual([x["url"] for x in response_sources(self.response())], ["https://a.test/leilao", "https://b.test/lote"])

    def test_resposta_sem_resultados(self):
        self.assertEqual(response_sources({"output": []}), [])

    def test_provider_configurado_chama_responses(self):
        client = Mock(); client.responses.create.return_value = self.response()
        results = OpenAIProvider(client=client, model="gpt-test").search("leilão", limit=1)
        self.assertEqual(results[0].url, "https://a.test/leilao")
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["tools"], [{"type": "web_search"}])
        self.assertEqual(kwargs["include"], ["web_search_call.action.sources"])

    def test_openai_usa_timeout_exclusivo(self):
        fake_openai = types.ModuleType("openai")
        factory = Mock()
        fake_openai.OpenAI = factory
        with patch.dict(
            os.environ,
            {
                "OPENAI_REQUEST_TIMEOUT": "60",
                "REQUEST_TIMEOUT": "15",
            },
            clear=True,
        ), patch.dict(sys.modules, {"openai": fake_openai}):
            OpenAIProvider(api_key="secret")
        factory.assert_called_once_with(
            api_key="secret",
            timeout=60.0,
            max_retries=1,
        )

    def test_erros_api_propagam_para_orquestrador(self):
        for error in (TimeoutError("timeout"), RuntimeError("429"), RuntimeError("500")):
            client = Mock(); client.responses.create.side_effect = error
            with self.assertRaises(type(error)):
                OpenAIProvider(client=client).search("x")


    def test_preflight_sem_chave(self):
        with patch.dict(os.environ, {}, clear=True):
            result = check()
        self.assertEqual((result.configurada, result.tipo_erro), (False, "CONFIG"))

    def test_preflight_mock_funcionando(self):
        client = Mock(); client.responses.create.return_value = self.response()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "segredo"}, clear=True):
            result = check(client)
        self.assertEqual((result.connection, result.web_search, result.fontes_teste), ("OK", "OK", 2))

    def test_classificacao_erros_openai(self):
        class Error(RuntimeError):
            def __init__(self, status, message): super().__init__(message); self.status_code = status
        self.assertEqual(classify_error(Error(401, "bad")), "AUTH")
        self.assertEqual(classify_error(Error(429, "bad")), "RATE_LIMIT")
        self.assertEqual(classify_error(Error(500, "server")), "API")
        self.assertEqual(classify_error(TimeoutError("timeout")), "NETWORK")

    def test_openai_401(self):
        class Error(RuntimeError):
            status_code = 401
        self.assertEqual(classify_error(Error("unauthorized")), "AUTH")

    def test_openai_403(self):
        class Error(RuntimeError):
            status_code = 403
        self.assertEqual(classify_error(Error("forbidden")), "AUTH")

    def test_openai_429(self):
        class Error(RuntimeError):
            status_code = 429
        self.assertEqual(classify_error(Error("rate limit")), "RATE_LIMIT")

    def test_openai_500(self):
        class Error(RuntimeError):
            status_code = 500
        self.assertEqual(classify_error(Error("server")), "API")

    def test_openai_timeout(self):
        self.assertEqual(classify_error(TimeoutError("timeout")), "NETWORK")


if __name__ == "__main__": unittest.main()
