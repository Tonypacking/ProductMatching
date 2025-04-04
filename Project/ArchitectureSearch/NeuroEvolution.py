import neat.config
import neat.genes
import numpy as np
import sklearn
import neat
import sklearn.discriminant_analysis
import sklearn.metrics
from typing import Sequence, Optional
import multiprocessing
import sklearn.metrics._base
from Dataset import Dataset
import configparser
import visualize
import ProMap

class Evolution:
    
    def __init__(self, config_path: str, dataset:Dataset = None, scaling : bool= False, dimension_reduction : str = 'raw'):
        self._dataset :Dataset = dataset
        self.dataset_name = self._dataset.dataset_name
        self.Best_network = None
        self._fitness_scaling = 1_000 
        self._transformer = None
        self._scaler = None

        self._neat_config = self._create_config(config_path, scaling=scaling, dimension_reduction=dimension_reduction)
        self._population = neat.Population(self._neat_config)
 
    @staticmethod
    def _binarize_prediction(x: float) -> int:
        """
        Binarize prediction to matching or None Matching
        """
        return 1 if x >= 0.5 else 0
    
    def _eval_genomes(self, genomes, config):
        """Evaluates genomes

        Args:
            genomes (_type_): genomes
            config (_type_): path to config file.
        """
        for id, genome in genomes:
            genome.fitness = self._dataset.train_set.shape[0]

            net = neat.nn.FeedForwardNetwork.create(genome=genome, config=config)

            predicted = np.array([Evolution._binarize_prediction(net.activate(x)[0]) for x in self._dataset.train_set])
            genome.fitness = sklearn.metrics.f1_score(y_pred=predicted, y_true=self._dataset.train_targets) * self._fitness_scaling

    def _create_config(self, config_path, scaling : bool = False, dimension_reduction: str = 'raw') -> neat.Config:
        """Creates config for genomes. If dataset's dimensions is reduced, it updates neat's input nodes.

        Args:
            config_path (_type_): Path to config file
            scaling (bool, optional): Scales features through StandardScaler before running neat. Defaults to False.
            dimension_reduction (str, optional): Reduces dimensions before running neat. Defaults to 'raw'.

        Returns:
            neat.Config: Neat configuration.
        """
        if scaling:
            self._scaler = self._dataset.scale_features()

        if dimension_reduction == 'lda' or dimension_reduction == 'pca':
            # number of input nodes are reduce. Dynamically change neat config also.
            self._transformer = self._dataset.reduce_dimensions(dimension_reduction)

            num_features = self._dataset.train_set.shape[1]
            parser = configparser.ConfigParser()
            parser.read(config_path)
            parser.set('DefaultGenome', 'num_inputs', str(num_features))

            with open(config_path, 'w') as f:
                parser.write(f)

        return neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet, neat.DefaultStagnation, config_path)

    def run(self, iterations: int = 50, parralel: bool = False) -> neat.nn.FeedForwardNetwork:
        """Runs the fining algorithm using neat.

        Args:
            iterations (int, optional): Number of generations in neat. Defaults to 50.
            parralel (bool, optional): Parralel evaluation of genomes. Defaults to False.

        Returns:
            neat.nn.FeedForwardNetwork: _description_
        """
        population = neat.Population(self._neat_config)

        population.add_reporter(neat.StdOutReporter(show_species_detail=True))
        self._statistics = neat.StatisticsReporter()
        population.add_reporter(self._statistics)
        if parralel:
            para_eval = neat.ParallelEvaluator(num_workers=multiprocessing.cpu_count(),eval_function=self._eval_genomes)

            self._winner = population.run(para_eval.eval_function, iterations)
        else:
            self._winner = population.run(self._eval_genomes, iterations)

        self.Best_network = neat.nn.FeedForwardNetwork.create(self._winner, self._neat_config)
        print(f"Winner {self._winner}")
        return self.Best_network
    
    def validate(self, test_set: Optional[Sequence] = None , target_set: Optional[Sequence] = None) -> dict[str, float]:
        """Va;odates best network against unseen data.

        Args:
            test_set (Optional[Sequence], optional): testing set. Defaults to None.
            target_set (Optional[Sequence], optional): testing true outpiut. Defaults to None.

        Returns:
            dict[str, float]: dictionary of name of a metric and metric's value
        """
        if test_set is None and target_set is None:
            predicted = np.array([Evolution._binarize_prediction(self.Best_network.activate(x)[0]) for x in self._dataset.test_set])
            target_set = self._dataset.test_targets

        elif (test_set is None and target_set is not None) or (test_set is not None and target_set is None):
            assert ValueError("Invalid test set or target set")
        else:
            predicted = np.array([Evolution._binarize_prediction(self.Best_network.activate(x)[0]) for x in test_set])

        return {
            'f1_score' : sklearn.metrics.f1_score(y_pred=predicted, y_true=target_set),
            'accuracy' : sklearn.metrics.accuracy_score(y_pred=predicted, y_true=target_set),
            'precision' : sklearn.metrics.precision_score(y_pred=predicted, y_true=target_set),
            'recall' : sklearn.metrics.recall_score(y_pred=predicted, y_true=target_set),
            'confusion_matrix' : sklearn.metrics.confusion_matrix(y_pred=predicted, y_true=target_set),
            'balanced_accuracy': sklearn.metrics.balanced_accuracy_score(y_pred=predicted, y_true=target_set),
        }

    def validate_all(self) -> list[tuple[str, dict[str, float]]]:
        """Validates against all promap datasets if feature count is the same.

        Returns:
            list[tuple[str, dict[str, float]]]: List of tuples with name of tested dataset and dictionary of metric and metrics value.
        """
        outputs = []
        for name in ProMap.ProductsDatasets.NAME_MAP:
            dataset= ProMap.ProductsDatasets.Load_by_name(name)

            if dataset.feature_labels.shape != self._dataset.feature_labels.shape:
                print(dataset.dataset_name, dataset.feature_labels.shape)
                print(self._dataset.dataset_name, self._dataset.feature_labels.shape)       
                print('datasets features are different, cannot transform them')
                continue

            if self._scaler:
                dataset.test_set = self._scaler.transform(dataset.test_set)
                
            if self._transformer:
                dataset.test_set = self._transformer.transform(dataset.test_set)

            outputs.append((dataset.dataset_name, self.validate(dataset.test_set, dataset.test_targets)))
        return outputs
    
    def plot_network(self, save_path :str, view = False ):
        """Plots the best genome's network

        Args:
            save_path (str): save path
            view (bool, optional): View of a plot durring runtime. Defaults to False.

        Returns:
            None: None
        """
        if self.Best_network is None:
            return # nothing to vizualize
        visualize.draw_net(config=self._neat_config,genome=self._winner, view=view, filename=save_path)
        
    def plot_statistics(self, save_path :str, view = False ):
        """Plots neat staticstics

        Args:
            save_path (str): save path
            view (bool, optional): View of a plot durring runtime. Defaults to False.

        Returns:
            None: None
        """
        if self._statistics is None:
            return # nothing to vizualize
        visualize.plot_stats(self._statistics, filename=save_path, view=view)