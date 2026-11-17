plugins {
    kotlin("jvm")
}

val ortVersion = "1.32.0"

kotlin {
    jvmToolchain(17)
}

dependencies {
    // Same Java API (ai.onnxruntime) in the desktop jar and the Android AAR:
    // the app module adds onnxruntime-android, tests use the desktop jar.
    compileOnly("com.microsoft.onnxruntime:onnxruntime:$ortVersion")
    implementation("com.google.code.gson:gson:2.11.0")
    testImplementation("com.microsoft.onnxruntime:onnxruntime:$ortVersion")
    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    val repo = rootProject.projectDir.parentFile
    systemProperty("mt.modelDir", System.getProperty("mt.modelDir") ?: File(repo, "models/out/opus-mt-en-vi-onnx").path)
    systemProperty("mt.golden", System.getProperty("mt.golden") ?: File(repo, "models/out/golden_opus.json").path)
    testLogging { events("passed", "skipped", "failed"); showStandardStreams = true }
}
