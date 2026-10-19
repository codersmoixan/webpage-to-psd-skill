"""Validate viewport, screenshot, and output-size invariants for PSD capture jobs."""
from __future__ import annotations

import json
from pathlib import Path


class CaptureContractError(ValueError):
    """Raised when capture artifacts disagree about viewport or output dimensions."""


def _require(condition, message):
    if not condition:
        raise CaptureContractError(message)


def _positive_int(value, label):
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
             f'{label} must be a positive integer')
    return value


def _number(value, label):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool),
             f'{label} must be numeric')
    return value


def load_capture_dimensions(root):
    path = Path(root) / 'capture_dimensions.json'
    if not path.is_file():
        raise FileNotFoundError('capture_dimensions.json is required before PSD preparation')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureContractError(f'Cannot read capture_dimensions.json: {error}') from error
    _require(isinstance(data, dict), 'capture_dimensions.json must contain a JSON object')
    return data


def validate_capture_dimensions(root, before, after, screenshot_size,
                                requested_scale=1, strict_scale=False):
    """Validate the pre-build contract and return a normalized dimensions record."""
    dimensions = load_capture_dimensions(root)
    width_source = dimensions.get('widthSource')
    _require(width_source in ('explicit', 'default-1920'),
             'widthSource must be "explicit" or "default-1920"')
    requested_width = _positive_int(dimensions.get('requestedViewportWidth'),
                                    'requestedViewportWidth')
    if width_source == 'default-1920':
        _require(requested_width == 1920,
                 'default-1920 capture must request a 1920-pixel viewport')

    scale_source = dimensions.get('scaleSource')
    _require(scale_source in ('explicit', 'default-1'),
             'scaleSource must be "explicit" or "default-1"')
    recorded_scale = _positive_int(dimensions.get('requestedRenderScale'),
                                   'requestedRenderScale')
    _require(recorded_scale in (1, 2, 3, 4),
             'requestedRenderScale must be one of 1, 2, 3, or 4')
    if scale_source == 'default-1':
        _require(recorded_scale == 1, 'default-1 capture must request 1x output')
    else:
        _require(strict_scale,
                 'Explicit output scale requires --strict-render-scale; silent reduction is not allowed')
    _require(requested_scale == recorded_scale,
             f'CLI render scale {requested_scale} does not match capture contract {recorded_scale}')

    measured_width = _positive_int(dimensions.get('measuredInnerWidth'),
                                   'measuredInnerWidth')
    measured_height = _positive_int(dimensions.get('measuredInnerHeight'),
                                    'measuredInnerHeight')
    client_width = _positive_int(dimensions.get('clientWidth'), 'clientWidth')
    scrollbar_width = dimensions.get('scrollbarWidth')
    _require(isinstance(scrollbar_width, int) and not isinstance(scrollbar_width, bool)
             and scrollbar_width >= 0, 'scrollbarWidth must be a non-negative integer')
    pixel_ratio = _number(dimensions.get('devicePixelRatio'), 'devicePixelRatio')
    _require(pixel_ratio > 0, 'devicePixelRatio must be greater than zero')
    screenshot_width = _positive_int(dimensions.get('screenshotWidth'), 'screenshotWidth')
    screenshot_height = _positive_int(dimensions.get('screenshotHeight'), 'screenshotHeight')

    _require(measured_width == requested_width,
             f'Measured innerWidth {measured_width} differs from requested viewport {requested_width}')
    _require(client_width + scrollbar_width == measured_width,
             'clientWidth + scrollbarWidth must equal measuredInnerWidth')
    _require(tuple(screenshot_size) == (screenshot_width, screenshot_height),
             'Saved reference screenshot dimensions differ from capture_dimensions.json')
    _require(screenshot_width == requested_width,
             f'Reference screenshot width {screenshot_width} differs from requested viewport '
             f'{requested_width}; recapture without width loss')

    for label, state in (('web_dom.json', before), ('web_dom_after.json', after)):
        _require(state.get('width') == measured_width,
                 f'{label} innerWidth differs from capture_dimensions.json')
        _require(state.get('viewportHeight') == measured_height,
                 f'{label} innerHeight differs from capture_dimensions.json')
        _require(state.get('clientWidth') == client_width,
                 f'{label} clientWidth differs from capture_dimensions.json')
        _require(state.get('scrollbarWidth') == scrollbar_width,
                 f'{label} scrollbarWidth differs from capture_dimensions.json')
        _require(abs(_number(state.get('ratio'), f'{label} devicePixelRatio') - pixel_ratio) < 1e-9,
                 f'{label} devicePixelRatio differs from capture_dimensions.json')
        _require(state.get('height') == screenshot_height,
                 f'{label} document height differs from reference screenshot height')

    return dict(dimensions)


def finalize_capture_dimensions(dimensions, screenshot_size, effective_scale):
    """Add values determined during preparation and return the completed record."""
    width, height = screenshot_size
    result = dict(dimensions)
    result['effectiveRenderScale'] = effective_scale
    result['finalPSDWidth'] = width * effective_scale
    result['finalPSDHeight'] = height * effective_scale
    return result


def verify_prepared_dimensions(root, manifest):
    """Ensure a prepared manifest still matches its completed capture contract."""
    dimensions = load_capture_dimensions(root)
    scale = _positive_int(dimensions.get('effectiveRenderScale'), 'effectiveRenderScale')
    expected_width = _positive_int(dimensions.get('finalPSDWidth'), 'finalPSDWidth')
    expected_height = _positive_int(dimensions.get('finalPSDHeight'), 'finalPSDHeight')
    _require(manifest.get('renderScale') == scale,
             'Prepared render scale differs from capture_dimensions.json')
    _require(manifest.get('width') * scale == expected_width,
             'Prepared PSD width differs from capture_dimensions.json')
    _require(manifest.get('height') * scale == expected_height,
             'Prepared PSD height differs from capture_dimensions.json')
    return dimensions
