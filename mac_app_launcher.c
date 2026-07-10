#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void dirname_in_place(char *path) {
    char *slash = strrchr(path, '/');
    if (slash == NULL) {
        strcpy(path, ".");
        return;
    }

    if (slash == path) {
        path[1] = '\0';
        return;
    }

    *slash = '\0';
}

static int project_files_exist(const char *project_dir) {
    char python_path[PATH_MAX];
    char app_path[PATH_MAX];

    snprintf(
        python_path,
        sizeof(python_path),
        "%s/.venv313/bin/python",
        project_dir
    );
    snprintf(app_path, sizeof(app_path), "%s/scheduler_gui.py", project_dir);

    return access(python_path, X_OK) == 0 && access(app_path, R_OK) == 0;
}

int main(void) {
    char executable_path[PATH_MAX];
    uint32_t executable_path_size = sizeof(executable_path);

    if (_NSGetExecutablePath(executable_path, &executable_path_size) != 0) {
        fprintf(stderr, "Could not resolve app executable path.\n");
        return 1;
    }

    char resolved_executable_path[PATH_MAX];
    if (realpath(executable_path, resolved_executable_path) == NULL) {
        perror("realpath");
        return 1;
    }

    char app_bundle[PATH_MAX];
    strncpy(app_bundle, resolved_executable_path, sizeof(app_bundle));
    app_bundle[sizeof(app_bundle) - 1] = '\0';
    dirname_in_place(app_bundle); /* MacOS */
    dirname_in_place(app_bundle); /* Contents */
    dirname_in_place(app_bundle); /* .app */

    char project_dir[PATH_MAX];
    strncpy(project_dir, app_bundle, sizeof(project_dir));
    project_dir[sizeof(project_dir) - 1] = '\0';
    dirname_in_place(project_dir);

    if (!project_files_exist(project_dir)) {
        strncpy(
            project_dir,
            "/Users/benwilton/horse-show-scheduler",
            sizeof(project_dir)
        );
        project_dir[sizeof(project_dir) - 1] = '\0';
    }

    char python_path[PATH_MAX];
    char app_path[PATH_MAX];

    snprintf(
        python_path,
        sizeof(python_path),
        "%s/.venv313/bin/python",
        project_dir
    );
    snprintf(app_path, sizeof(app_path), "%s/scheduler_gui.py", project_dir);

    if (access(python_path, X_OK) != 0) {
        fprintf(stderr, "Could not find Python app environment: %s\n", python_path);
        return 1;
    }

    if (access(app_path, R_OK) != 0) {
        fprintf(stderr, "Could not find scheduler_gui.py: %s\n", app_path);
        return 1;
    }

    if (chdir(project_dir) != 0) {
        perror("chdir");
        return 1;
    }

    char *const argv[] = {python_path, app_path, NULL};
    execv(python_path, argv);
    perror("execv");
    return 1;
}
