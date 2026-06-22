import org.gradle.api.file.Directory

buildscript {
    repositories {
        google()
        mavenCentral()
        // ✅ Repositorios necesarios para flutter_background_geolocation
        maven { url = uri("https://maven.transistorsoft.com") }
        maven { url = uri("https://jitpack.io") }
    }
    dependencies {
        classpath("com.android.tools.build:gradle:9.1.0")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.22")
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
        // ✅ Mirror público de Transistorsoft en GitHub
        maven { url = uri("https://github.com/transistorsoft/maven-repo/raw/master/") }
        maven { url = uri("https://jitpack.io") }
    }
}


// ✅ Configuración de los directorios de build
val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

subprojects {
    project.evaluationDependsOn(":app")
}

// ✅ Tarea para limpiar compilaciones
tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
