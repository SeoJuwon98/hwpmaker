from __future__ import annotations

import base64
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from app.services.report_hwpx.dom import HP_NS, HS_NS


NS = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": HP_NS,
    "hs": HS_NS,
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "opf": "http://www.idpf.org/2007/opf",
    "ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
    "odf": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

HH = f"{{{NS['hh']}}}"
OPF = f"{{{NS['opf']}}}"

BLANK_PREVIEW_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO0pQe8AAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class BinaryAsset:
    asset_id: str
    image_format: str
    data: bytes

    @property
    def filename(self) -> str:
        return f"{self.asset_id}.{self.image_format.lower()}"

    @property
    def media_type(self) -> str:
        return f"image/{self.image_format.lower()}"


def write_report_archive(*, target_path: Path, section_xml: ET.Element, header_template_path: Path, binary_assets: Iterable[BinaryAsset]) -> None:
    assets = list(binary_assets)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/content.hpf", _build_content_hpf(assets))
        archive.writestr("Contents/header.xml", _build_header_xml(header_template_path, assets))
        archive.writestr("Contents/section0.xml", ET.tostring(section_xml, encoding="utf-8", xml_declaration=True))
        archive.writestr("META-INF/container.rdf", _container_rdf())
        archive.writestr("META-INF/container.xml", _container_xml())
        archive.writestr("META-INF/manifest.xml", _manifest_xml())
        archive.writestr("Preview/PrvImage.png", BLANK_PREVIEW_PNG)
        archive.writestr("Preview/PrvText.txt", "")
        archive.writestr("settings.xml", _settings_xml())
        archive.writestr("version.xml", _version_xml())
        for asset in assets:
            archive.writestr(f"BinData/{asset.filename}", asset.data)


def validate_report_archive(path: Path) -> None:
    required_entries = {
        "mimetype",
        "Contents/content.hpf",
        "Contents/header.xml",
        "Contents/section0.xml",
        "META-INF/container.rdf",
        "META-INF/container.xml",
        "META-INF/manifest.xml",
        "Preview/PrvImage.png",
        "Preview/PrvText.txt",
        "settings.xml",
        "version.xml",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = required_entries - names
        if missing:
            raise ValueError(f"missing hwpx entries: {sorted(missing)}")
        mimetype = archive.read("mimetype").decode("utf-8")
        if mimetype != "application/hwp+zip":
            raise ValueError("invalid mimetype")
        content_root = ET.fromstring(archive.read("Contents/content.hpf"))
        header_root = ET.fromstring(archive.read("Contents/header.xml"))
        section_root = ET.fromstring(archive.read("Contents/section0.xml"))

        if not section_root.tag.endswith("sec"):
            raise ValueError("invalid section root")

        manifest_items = {
            item.get("href", "")
            for item in content_root.findall(f".//{OPF}manifest/{OPF}item")
        }
        if "Contents/header.xml" not in manifest_items or "Contents/section0.xml" not in manifest_items:
            raise ValueError("content manifest missing required entries")

        header_assets = {
            item.get("href", "")
            for item in header_root.findall(f".//{HH}binDataList/{HH}binData")
        }
        content_assets = {href for href in manifest_items if href.startswith("BinData/")}
        archive_assets = {name for name in names if name.startswith("BinData/")}
        if header_assets != content_assets:
            raise ValueError("header/content embedded assets mismatch")
        if content_assets != archive_assets:
            raise ValueError("embedded asset files missing from archive")


def _build_header_xml(header_template_path: Path, binary_assets: list[BinaryAsset]) -> bytes:
    header_bytes = header_template_path.read_bytes()
    if not binary_assets:
        return header_bytes
    root = ET.fromstring(header_bytes)
    ref_list = root.find(f"{HH}refList")
    if ref_list is None:
        return header_bytes
    existing = ref_list.find(f"{HH}binDataList")
    if existing is not None:
        ref_list.remove(existing)
    bin_data_list = ET.Element(f"{HH}binDataList", {"itemCnt": str(len(binary_assets))})
    for asset in binary_assets:
        ET.SubElement(
            bin_data_list,
            f"{HH}binData",
            {
                "id": asset.asset_id,
                "href": f"BinData/{asset.filename}",
                "media-type": asset.media_type,
                "isEmbeded": "1",
                "sub-path": "",
            },
        )
    ref_list.append(bin_data_list)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _build_content_hpf(binary_assets: list[BinaryAsset]) -> bytes:
    root = ET.Element(f"{OPF}package", {"version": "", "unique-identifier": "", "id": ""})
    metadata = ET.SubElement(root, f"{OPF}metadata")
    ET.SubElement(metadata, f"{OPF}title")
    ET.SubElement(metadata, f"{OPF}language").text = "ko"
    _meta(metadata, "creator", "hwpmaker")
    _meta(metadata, "subject", "")
    _meta(metadata, "description", "")
    _meta(metadata, "lastsaveby", "hwpmaker")
    _meta(metadata, "CreatedDate", "")
    _meta(metadata, "ModifiedDate", "")
    _meta(metadata, "date", "")
    _meta(metadata, "keyword", "")

    manifest = ET.SubElement(root, f"{OPF}manifest")
    ET.SubElement(manifest, f"{OPF}item", {"id": "header", "href": "Contents/header.xml", "media-type": "application/xml"})
    ET.SubElement(manifest, f"{OPF}item", {"id": "section0", "href": "Contents/section0.xml", "media-type": "application/xml"})
    ET.SubElement(manifest, f"{OPF}item", {"id": "settings", "href": "settings.xml", "media-type": "application/xml"})
    for asset in binary_assets:
        ET.SubElement(
            manifest,
            f"{OPF}item",
            {"id": asset.asset_id, "href": f"BinData/{asset.filename}", "media-type": asset.media_type, "isEmbeded": "1"},
        )

    spine = ET.SubElement(root, f"{OPF}spine")
    ET.SubElement(spine, f"{OPF}itemref", {"idref": "header", "linear": "yes"})
    ET.SubElement(spine, f"{OPF}itemref", {"idref": "section0", "linear": "yes"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _meta(parent: ET.Element, name: str, text: str) -> None:
    node = ET.SubElement(parent, f"{OPF}meta", {"name": name, "content": "text"})
    node.text = text


def _container_rdf() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'


def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
        'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
        "<ocf:rootfiles>"
        '<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
        '<ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/>'
        '<ocf:rootfile full-path="META-INF/container.rdf" media-type="application/rdf+xml"/>'
        "</ocf:rootfiles>"
        "</ocf:container>"
    )


def _manifest_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'


def _settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
        'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
        '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="16"/>'
        "</ha:HWPApplicationSetting>"
    )


def _version_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
        'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0" '
        'os="1" xmlVersion="1.5" application="Hancom Office Hangul" '
        'appVersion="13, 0, 0, 1408 WIN32LEWindows_10"/>'
    )
