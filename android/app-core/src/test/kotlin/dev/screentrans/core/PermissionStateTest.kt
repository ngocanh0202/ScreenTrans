package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class PermissionStateTest {
    @Test
    fun `overlay permission comes first`() {
        for (n in listOf(true, false)) for (r in listOf(true, false)) assertEquals(Step.OVERLAY, nextStep(false, n, r))
    }

    @Test
    fun `then notifications, then capture, then running`() {
        assertEquals(Step.NOTIFICATIONS, nextStep(true, false, false))
        assertEquals(Step.CAPTURE, nextStep(true, true, false))
        assertEquals(Step.RUNNING, nextStep(true, true, true))
    }

    @Test
    fun `running service with notifications denied still shows running`() {
        assertEquals(Step.RUNNING, nextStep(true, false, true))
    }
}

class NotificationSkipTest {
    @Test
    fun `after notifications were asked once the user can continue without them`() {
        assertEquals(Step.CAPTURE, nextStep(true, false, false, notificationsAsked = true))
        assertEquals(Step.NOTIFICATIONS, nextStep(true, false, false, notificationsAsked = false))
    }
}
