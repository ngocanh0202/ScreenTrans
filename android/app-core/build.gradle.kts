plugins {
    kotlin("jvm")
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    api(project(":text-core"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("com.anthropic:anthropic-java:3.3.0")  // Claude (official SDK); Gemini / OpenAI / Kaggle use HttpURLConnection
    testImplementation(kotlin("test"))
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    val repo = rootProject.projectDir.parentFile
    val shared = System.getProperty("shared.dir") ?: File(repo, "shared").path
    systemProperty("shared.dir", shared)
    inputs.dir(shared)  // shared fixtures: editing them must re-run the tests
    testLogging { events("failed"); exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL }
}
