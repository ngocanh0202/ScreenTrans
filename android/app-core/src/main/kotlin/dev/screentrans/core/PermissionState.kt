package dev.screentrans.core

/** What the start screen asks for next. */
enum class Step { OVERLAY, NOTIFICATIONS, CAPTURE, RUNNING }

/**
 * Order: draw-over-apps permission -> notifications (Android 13+; pass true below 13) ->
 * screen-capture consent (starts the service) -> running. A running service stays RUNNING even if
 * notifications were revoked later; without the overlay permission nothing can be shown at all.
 */
fun nextStep(canDrawOverlays: Boolean, notificationsOk: Boolean, serviceRunning: Boolean): Step = when {
    !canDrawOverlays -> Step.OVERLAY
    serviceRunning -> Step.RUNNING
    !notificationsOk -> Step.NOTIFICATIONS
    else -> Step.CAPTURE
}
