plugins {
    id("com.android.application")
    kotlin("android")
}

val ortVersion = "1.32.0" // keep equal to mt-core and models/requirements.txt

android {
    namespace = "dev.screentrans.spike"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.screentrans.spike"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "0.0.1-spike"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    androidResources {
        noCompress += listOf("onnx", "json")
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":mt-core"))
    implementation("com.microsoft.onnxruntime:onnxruntime-android:$ortVersion")
    implementation("com.google.code.gson:gson:2.11.0")
}
