"""GUI strings — English and Portuguese."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from branding import APP_NAME, APP_TAGLINE

LanguageCode = str

LANGUAGE_CHOICES: tuple[tuple[str, LanguageCode], ...] = (
    ("English", "en"),
    ("Português", "pt"),
)
LANGUAGE_LABELS = [label for label, _ in LANGUAGE_CHOICES]
LANGUAGE_BY_LABEL = {label: code for label, code in LANGUAGE_CHOICES}
LANGUAGE_BY_CODE = {code: label for label, code in LANGUAGE_CHOICES}

DEFAULT_LANGUAGE: LanguageCode = "en"

# Scan worker preset count → translation key suffix
WORKER_PRESET_COUNTS = (1, 2, 3, 4, 5, 6, 7, 8)


@dataclass(frozen=True)
class Locale:
    code: LanguageCode
    strings: dict[str, str]
    pipeline: dict[str, tuple[str, str]]

    def t(self, key: str, **kwargs: object) -> str:
        text = self.strings.get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def pipeline_step(self, phase: str) -> tuple[str, str]:
        return self.pipeline.get(phase, (phase, ""))

    def worker_label(self, count: int) -> str:
        return self.t(f"worker_{count}")

    def inference_label(self, device: str) -> str:
        return self.t(f"inference_{device}")


def _en() -> Locale:
    return Locale(
        code="en",
        strings={
            "tagline": APP_TAGLINE,
            "label_input": "Input",
            "label_output": "Output",
            "label_naming_ref": "Naming ref",
            "browse": "Browse…",
            "folder_dialog_title": "Select folder",
            "label_ref_skip": "Ref folder skip",
            "hint_ref_skip": (
                "Folder levels up from each photo to the identity label "
                "(0 = folder that holds the image)"
            ),
            "label_group_faces": "Group if faces >",
            "hint_group_faces": (
                "Roster photos with more than this many faces may define separate "
                "classes; otherwise the whole batch is sorted as one class_001"
            ),
            "move_files": "Move files (leave empty source folders; unchecked = copy)",
            "duplicate_group": "Duplicate group photos into person folders",
            "label_bg_sensitivity": "Background face sensitivity",
            "sensitivity_strict": "strict — ignore distant background faces",
            "sensitivity_balanced": "balanced",
            "sensitivity_permissive": "permissive — keep smaller background faces",
            "label_scan_workers": "Scan workers",
            "hint_scan_workers": "More workers = faster scan, more RAM (~200 MB per extra worker)",
            "worker_1": "1 — safe (default)",
            "worker_2": "2 — balanced",
            "worker_3": "3",
            "worker_4": "4",
            "worker_5": "5",
            "worker_6": "6",
            "worker_7": "7",
            "worker_8": "8 — max preset",
            "worker_custom": "Custom…",
            "label_acceleration": "Acceleration",
            "inference_auto": "Auto",
            "inference_cpu": "CPU only",
            "inference_coreml": "Apple GPU (CoreML)",
            "inference_cuda": "NVIDIA GPU (CUDA)",
            "accel_hint_default": "Uses Apple/NVIDIA GPU when available (Auto)",
            "accel_hint_coreml": "Apple GPU (CoreML) available — Auto uses it",
            "accel_hint_cuda": "NVIDIA GPU (CUDA) available — Auto uses it",
            "accel_hint_cpu": "No GPU backend detected — CPU only on this Mac",
            "btn_sort": "Sort photos",
            "btn_cancel": "Cancel",
            "activity_log": "Activity log",
            "ready_hint": (
                "Choose input and output folders, then click Sort photos. "
                "Progress appears here step by step."
            ),
            "ready_to_sort": "Ready to sort",
            "preparing": "Preparing…",
            "preparing_caption": "Starting up — loading face recognition models",
            "preparing_detail": "This may take a moment on the first run.",
            "complete": "Complete",
            "complete_detail": "See the activity log below for details.",
            "working": "Working",
            "step_save_photos": "Save photos",
            "step_move_photos": "Move photos",
            "detail_cached_names": "Using saved name library — no re-scan needed",
            "detail_photo": "Photo {current} of {total}",
            "detail_file": "File {current} of {total}",
            "detail_name": "Name {current} of {total}",
            "detail_step": "Step {current} of {total}",
            "loading_models": "Loading models ({device})…",
            "finish_copied": (
                "All done — photos were copied into the output folder. "
                "Your original input folder was left unchanged."
            ),
            "finish_moved": (
                "All done — photos were moved into the output folder. "
                "Empty source folders may remain."
            ),
            "error_headline": "Something went wrong",
            "error_caption": "The sort did not finish.",
            "error_already_running": "Already running.",
            "error_input_missing": "Input folder does not exist.",
            "error_output_missing": "Choose an output folder.",
            "error_group_faces_int": "Group face threshold must be a whole number.",
            "error_group_faces_min": "Group face threshold must be at least 1.",
            "error_ref_skip_int": "Ref folder skip must be a whole number.",
            "error_ref_skip_min": "Ref folder skip must be 0 or greater.",
            "error_workers_int": "Custom scan workers must be a whole number.",
            "error_workers_min": "Scan workers must be at least 1.",
            "error_naming_ref": "Naming reference folder does not exist.",
            "sort_cancelled": "Sort cancelled",
            "sort_cancelled_detail": "No photos were saved. The next run will use a new output folder.",
            "log_output": "Output: {path}",
            "log_roster_groups": "Roster groups: {count}",
            "log_person_clusters": "Person clusters: {count}",
            "log_moves": "Moves: {matched} matched, {unmatched} unmatched",
            "log_copies": "Copies: {matched} matched, {unmatched} unmatched",
            "log_file": "Log: {path}",
            "log_timing": (
                "Timing — scan {scan:.1f}s, cluster {cluster:.1f}s, "
                "copy {copy:.1f}s · {faces} faces in {with_face}/{images} images"
            ),
            "log_person_names": "Person names:",
            "resource_memory": "Memory {mem}",
            "resource_cpu": "CPU {cpu:.0f}%",
            "resource_workers": "Workers {count}",
            "resource_processes": "{count} processes",
            "resource_elapsed": "Elapsed {time}",
        },
        pipeline={
            "scan": ("Find faces", "Looking at each photo"),
            "cluster": ("Group people", "Matching faces that belong together"),
            "naming": ("Load names", "Reading your reference library"),
            "naming_match": ("Apply names", "Labeling each group"),
            "sort": ("Save photos", "Placing files in folders"),
        },
    )


def _pt() -> Locale:
    return Locale(
        code="pt",
        strings={
            "tagline": (
                "InsightFace CNN · agrupamento · correspondência por referência — no dispositivo"
            ),
            "label_input": "Entrada",
            "label_output": "Saída",
            "label_naming_ref": "Ref. de nomes",
            "browse": "Procurar…",
            "folder_dialog_title": "Selecionar pasta",
            "label_ref_skip": "Saltar pastas ref.",
            "hint_ref_skip": (
                "Níveis de pasta acima de cada foto até ao nome da identidade "
                "(0 = pasta que contém a foto)"
            ),
            "label_group_faces": "Grupo se rostos >",
            "hint_group_faces": (
                "Fotos de roster com mais rostos que este limiar podem definir turmas "
                "separadas; caso contrário todo o lote fica num único class_001"
            ),
            "move_files": "Mover ficheiros (pastas de origem ficam vazias; desmarcado = copiar)",
            "duplicate_group": "Duplicar fotos de grupo nas pastas de cada pessoa",
            "label_bg_sensitivity": "Sensibilidade a rostos de fundo",
            "sensitivity_strict": "rigoroso — ignora rostos distantes no fundo",
            "sensitivity_balanced": "equilibrado",
            "sensitivity_permissive": "permissivo — mantém rostos pequenos no fundo",
            "label_scan_workers": "Workers de análise",
            "hint_scan_workers": "Mais workers = análise mais rápida, mais RAM (~200 MB por worker)",
            "worker_1": "1 — seguro (predefinição)",
            "worker_2": "2 — equilibrado",
            "worker_3": "3",
            "worker_4": "4",
            "worker_5": "5",
            "worker_6": "6",
            "worker_7": "7",
            "worker_8": "8 — máximo predefinido",
            "worker_custom": "Personalizado…",
            "label_acceleration": "Aceleração",
            "inference_auto": "Automático",
            "inference_cpu": "Apenas CPU",
            "inference_coreml": "GPU Apple (CoreML)",
            "inference_cuda": "GPU NVIDIA (CUDA)",
            "accel_hint_default": "Usa GPU Apple/NVIDIA quando disponível (Automático)",
            "accel_hint_coreml": "GPU Apple (CoreML) disponível — Automático usa-a",
            "accel_hint_cuda": "GPU NVIDIA (CUDA) disponível — Automático usa-a",
            "accel_hint_cpu": "Sem GPU detetada — apenas CPU neste Mac",
            "btn_sort": "Ordenar fotos",
            "btn_cancel": "Cancelar",
            "activity_log": "Registo de atividade",
            "ready_hint": (
                "Escolha as pastas de entrada e saída e clique em Ordenar fotos. "
                "O progresso aparece aqui passo a passo."
            ),
            "ready_to_sort": "Pronto para ordenar",
            "preparing": "A preparar…",
            "preparing_caption": "A iniciar — a carregar modelos de reconhecimento facial",
            "preparing_detail": "Na primeira execução pode demorar um momento.",
            "complete": "Concluído",
            "complete_detail": "Consulte o registo de atividade abaixo para detalhes.",
            "working": "A processar",
            "step_save_photos": "Guardar fotos",
            "step_move_photos": "Mover fotos",
            "detail_cached_names": "A usar biblioteca de nomes guardada — sem nova análise",
            "detail_photo": "Foto {current} de {total}",
            "detail_file": "Ficheiro {current} de {total}",
            "detail_name": "Nome {current} de {total}",
            "detail_step": "Passo {current} de {total}",
            "loading_models": "A carregar modelos ({device})…",
            "finish_copied": (
                "Concluído — as fotos foram copiadas para a pasta de saída. "
                "A pasta de entrada original não foi alterada."
            ),
            "finish_moved": (
                "Concluído — as fotos foram movidas para a pasta de saída. "
                "As pastas de origem podem ter ficado vazias."
            ),
            "error_headline": "Ocorreu um problema",
            "error_caption": "A ordenação não terminou.",
            "error_already_running": "Já está em execução.",
            "error_input_missing": "A pasta de entrada não existe.",
            "error_output_missing": "Escolha uma pasta de saída.",
            "error_group_faces_int": "O limiar de rostos do grupo tem de ser um número inteiro.",
            "error_group_faces_min": "O limiar de rostos do grupo tem de ser pelo menos 1.",
            "error_ref_skip_int": "Saltar pastas ref. tem de ser um número inteiro.",
            "error_ref_skip_min": "Saltar pastas ref. tem de ser 0 ou superior.",
            "error_workers_int": "Workers personalizados têm de ser um número inteiro.",
            "error_workers_min": "O número de workers tem de ser pelo menos 1.",
            "error_naming_ref": "A pasta de referência de nomes não existe.",
            "sort_cancelled": "Ordenação cancelada",
            "sort_cancelled_detail": "Nenhuma foto foi guardada. A próxima execução usará uma nova pasta de saída.",
            "log_output": "Saída: {path}",
            "log_roster_groups": "Grupos de roster: {count}",
            "log_person_clusters": "Clusters de pessoas: {count}",
            "log_moves": "Movidos: {matched} correspondidos, {unmatched} sem correspondência",
            "log_copies": "Cópias: {matched} correspondidos, {unmatched} sem correspondência",
            "log_file": "Registo: {path}",
            "log_timing": (
                "Tempos — análise {scan:.1f}s, agrupamento {cluster:.1f}s, "
                "cópia {copy:.1f}s · {faces} rostos em {with_face}/{images} fotos"
            ),
            "log_person_names": "Nomes das pessoas:",
            "resource_memory": "Memória {mem}",
            "resource_cpu": "CPU {cpu:.0f}%",
            "resource_workers": "Workers {count}",
            "resource_processes": "{count} processos",
            "resource_elapsed": "Decorrido {time}",
        },
        pipeline={
            "scan": ("Detetar rostos", "A analisar cada foto"),
            "cluster": ("Agrupar pessoas", "A juntar rostos semelhantes"),
            "naming": ("Carregar nomes", "A ler a biblioteca de referência"),
            "naming_match": ("Aplicar nomes", "A etiquetar cada grupo"),
            "sort": ("Guardar fotos", "A colocar ficheiros nas pastas"),
        },
    )


LOCALES: dict[LanguageCode, Locale] = {
    "en": _en(),
    "pt": _pt(),
}


def get_locale(code: str | None) -> Locale:
    if code and code in LOCALES:
        return LOCALES[code]
    return LOCALES[DEFAULT_LANGUAGE]


def worker_labels(locale: Locale) -> list[str]:
    labels = [locale.worker_label(n) for n in WORKER_PRESET_COUNTS]
    labels.append(locale.t("worker_custom"))
    return labels


def worker_value_from_label(locale: Locale, label: str) -> int:
    for count in WORKER_PRESET_COUNTS:
        if label == locale.worker_label(count):
            return count
    if label == locale.t("worker_custom"):
        return -1
    return 1


def worker_label_for_count(locale: Locale, count: int) -> str:
    if count in WORKER_PRESET_COUNTS:
        return locale.worker_label(count)
    return locale.t("worker_custom")


def inference_menu(locale: Locale, accelerators: dict[str, bool]) -> tuple[list[str], dict[str, str], dict[str, str]]:
    options: list[tuple[str, str]] = [
        (locale.t("inference_auto"), "auto"),
        (locale.t("inference_cpu"), "cpu"),
    ]
    if accelerators.get("coreml"):
        options.append((locale.t("inference_coreml"), "coreml"))
    if accelerators.get("cuda"):
        options.append((locale.t("inference_cuda"), "cuda"))
    labels = [label for label, _ in options]
    label_to_value = {label: value for label, value in options}
    value_to_label = {value: label for label, value in options}
    return labels, label_to_value, value_to_label


def friendly_step_detail(
    locale: Locale,
    phase: str,
    message: str,
    current: int,
    total: int,
) -> str:
    if "cached reference" in message.lower() or "cached naming" in message.lower():
        return locale.t("detail_cached_names")
    if total > 0:
        if phase == "scan":
            count_line = locale.t("detail_photo", current=current, total=total)
        elif phase == "sort":
            count_line = locale.t("detail_file", current=current, total=total)
        elif phase in {"naming", "naming_match"}:
            count_line = locale.t("detail_name", current=current, total=total)
        else:
            count_line = locale.t("detail_step", current=current, total=total)
    else:
        count_line = ""

    if ": " in message:
        tail = message.split(": ", 1)[-1].strip()
        if tail and not tail.startswith("["):
            return f"{count_line} · {tail}" if count_line else tail
    return count_line or message


def format_resource_line_localized(
    locale: Locale,
    *,
    memory_mb: float,
    cpu_percent: float,
    scan_workers: int,
    elapsed_seconds: float | None,
    inference: str | None,
    process_count: int,
    format_memory: Callable[[float], str],
    format_duration: Callable[[float], str],
) -> str:
    parts: list[str] = []
    if inference:
        parts.append(inference)
    parts.append(locale.t("resource_memory", mem=format_memory(memory_mb)))
    parts.append(locale.t("resource_cpu", cpu=cpu_percent))
    parts.append(locale.t("resource_workers", count=scan_workers))
    if process_count > 1:
        parts.append(locale.t("resource_processes", count=process_count))
    if elapsed_seconds is not None:
        parts.append(locale.t("resource_elapsed", time=format_duration(elapsed_seconds)))
    return " · ".join(parts)
